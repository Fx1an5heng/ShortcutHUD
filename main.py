# shortcut_overlay/main.py
"""
Main application module for the Shortcut Overlay.

This module initializes and runs the Qt application, sets up the main components
such as the overlay window, configuration manager, foreground app monitor,
keyboard handler, and system tray icon. It also handles translations
and global application settings.
"""

import sys
import os
from collections.abc import Mapping
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QObject, QTranslator, QLocale, QLibraryInfo, Signal, Slot, Qt

# Define the application's root directory for resource access.
# Frozen (PyInstaller onedir) builds read bundled resources next to the
# executable so portable copies keep working; source runs read from the repo.
if getattr(sys, "frozen", False):
    APP_ROOT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Ensure the 'scripts' directory is in the Python path for module imports.
SCRIPTS_DIR = os.path.join(APP_ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

try:
    from scripts.__version__ import __version__
except ImportError:
    __version__ = "0.0.0-dev" # Fallback version if not found.

# Import core application components.
from scripts.overlay_keyboard import OverlayKeyboardWindow
from scripts.application_identity import ApplicationIdentityRuntime
from scripts.current_application_candidate import CurrentApplicationCandidateTracker
from scripts.config_manager import ConfigManager
from scripts.foreground_monitor import ForegroundMonitor
from scripts.fullscreen_detection import WindowsFullscreenDetector
from scripts.game_guard_runtime import GameGuardRuntime
from scripts.keyboard_handler import KeyboardHandler
from scripts.shortcut_hud import ShortcutHudWindow
from scripts.shortcut_hud_controller import ShortcutHudController
from scripts.suppression_policy import PresentationIntent, SuppressionPolicy
from scripts.user_shortcut_store import UserShortcutStore, get_profile_display_names
from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.win_discovery_proxy import WinDiscoveryProxy
from scripts.settings_dialog import SettingsDialog, AboutDialog


class _WinReleaseBridge(QObject):
    """Queue physical Win releases from the native hook onto the Qt thread."""

    physical_win_released = Signal(int)


def load_user_shortcut_store(
    path: str | os.PathLike[str] | None = None,
) -> UserShortcutStore:
    """Load the production or injected user profile file once at startup."""

    store = UserShortcutStore(path)
    store.load()
    return store


def load_quick_hud_selection_store(
    path: str | os.PathLike[str] | None = None,
) -> QuickHudSelectionStore:
    """Load independent Catalog selection state once at startup."""

    store = QuickHudSelectionStore(path)
    store.load()
    return store


class ShortcutOverlayApplication(QApplication):
    """
    The main application class, orchestrating all core components and managing
    the application lifecycle.
    """
    def __init__(self, argv: List[str]):
        """
        Initializes the ShortcutOverlayApplication.

        Sets up application settings, translation services, core components like
        the overlay window and input handlers, and the system tray icon.

        Args:
            argv: Command line arguments passed to the application.
        """
        super().__init__(argv)
        # The application should not quit when the last window (overlay) is closed.
        # Exit is handled via the system tray menu.
        app_icon = QIcon()
        icon_path_png = os.path.join(APP_ROOT_DIR, "assets", "app_icon.png")
        icon_path_ico = os.path.join(APP_ROOT_DIR, "assets", "app_icon.ico") # ICO for Windows often preferred

        if os.path.exists(icon_path_ico): # Prefer .ico for Windows window icons
            app_icon.addFile(icon_path_ico)
        elif os.path.exists(icon_path_png):
            app_icon.addFile(icon_path_png)
        else:
            print(f"Warning: Application icon (app_icon.ico/png) not found in assets. Using fallback.")
            # Fallback to a themed icon or leave it to OS default
            app_icon = QIcon.fromTheme("application-x-executable") 
        
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.setQuitOnLastWindowClosed(False)

        print(f"Starting ShortcutHUD version {__version__}")

        # Initialize configuration paths and manager.
        config_dir = os.path.join(APP_ROOT_DIR, "config")
        os.makedirs(config_dir, exist_ok=True)
        shortcuts_path = os.path.join(config_dir, "shortcuts.json")
        settings_path = os.path.join(config_dir, "settings.json")
        self.config_mgr: ConfigManager = ConfigManager(shortcuts_path, settings_path)
        self.config_mgr.initialize_configs()
        self.user_shortcut_store = load_user_shortcut_store()
        self.quick_hud_selection_store = load_quick_hud_selection_store()
        user_profiles = self.user_shortcut_store.snapshot()

        # Setup translation services.
        self.translator: QTranslator = QTranslator()
        self.qt_translator: QTranslator = QTranslator()
        self.load_translations()

        # Initialize core application components.
        self.overlay_window: OverlayKeyboardWindow = OverlayKeyboardWindow(self.config_mgr)
        self.shortcut_hud_window: ShortcutHudWindow = ShortcutHudWindow(
            application_display_names=(
                self.user_shortcut_store.display_names_snapshot()
            )
        )
        self.monitor: ForegroundMonitor = ForegroundMonitor()
        self.application_identity = ApplicationIdentityRuntime(
            self.monitor,
            parent=self,
        )
        self.current_application_candidate = CurrentApplicationCandidateTracker(
            lambda: self.monitor.current_hwnd,
            parent=self,
        )
        self.kb_handler: KeyboardHandler = KeyboardHandler()
        self.suppression_policy = SuppressionPolicy()
        self.game_guard_runtime = GameGuardRuntime(
            self.suppression_policy,
            WindowsFullscreenDetector(),
            lambda: self.application_identity.current_app_name,
            self.config_mgr.get_all_settings(),
            parent=self,
        )
        self._win_release_bridge = _WinReleaseBridge(self)
        self.win_discovery_proxy: WinDiscoveryProxy = WinDiscoveryProxy(
            self._win_release_bridge.physical_win_released.emit
        )
        self.hud_controller: ShortcutHudController = ShortcutHudController(
            self.config_mgr,
            self.application_identity,
            self.shortcut_hud_window,
            self.win_discovery_proxy,
            parent=self,
            user_profiles=user_profiles,
            suppression_policy=self.suppression_policy,
            selection_store=self.quick_hud_selection_store,
        )

        # Initialize and configure the system tray icon.
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self.game_mode_action: Optional[QAction] = None
        self._initialize_tray_icon_object() # Create the QSystemTrayIcon object
        self._update_tray_icon_ui()         # Populate its UI elements.

        self.aboutToQuit.connect(self.overlay_window.save_geometry_on_quit) # Save overlay geometry on quit.
        
        # Connect signals and slots for inter-component communication.
        self.setup_connections()

        # Start services. The legacy overlay stays hidden until opened from the tray.
        self.kb_handler.start_listening()
        if not self.win_discovery_proxy.start():
            error = self.win_discovery_proxy.last_error
            print(
                f"Warning: Win discovery proxy unavailable; using native Win behavior. {error!r}"
            )
        if not self.application_identity.start():
            error = self.application_identity.event_hook_error
            print(
                "Warning: WPS focus event hook unavailable; "
                f"foreground polling remains active. Win32 error: {error!r}"
            )
        self.monitor.check_foreground_app() # Perform an initial check of the active application.
        # Synchronize the overlay with the current keyboard modifier state.
        self.overlay_window.on_modifiers_changed(self.kb_handler._active_modifiers.copy())
        self.hud_controller.on_modifiers_changed(self.kb_handler._active_modifiers.copy())

    def load_translations(self) -> None:
        """
        Loads application-specific and Qt base translations.
        Attempts to load for the configured locale, then its base language,
        and uses system defaults for Qt translations if specific ones aren't found.
        """
        lang_setting: str = self.config_mgr.get_setting("language", QLocale.system().name())
        locale_to_load: QLocale = QLocale(lang_setting)
        i18n_dir: str = os.path.join(APP_ROOT_DIR, "i18n")
        os.makedirs(i18n_dir, exist_ok=True) # Ensure translation directory exists.

        # Load application-specific translations (e.g., "shortcut_overlay_en_US.qm").
        if self.translator.load(locale_to_load, "shortcut_overlay", "_", i18n_dir):
            self.installTranslator(self.translator)
        else: # Fallback to base language (e.g., "en" from "en_US").
            if "_" in locale_to_load.name():
                base_locale_name = locale_to_load.name().split('_')[0]
                base_locale = QLocale(base_locale_name)
                if self.translator.load(base_locale, "shortcut_overlay", "_", i18n_dir):
                    self.installTranslator(self.translator)

        # Load Qt base translations (e.g., "qtbase_en_US.qm" for standard dialog buttons).
        qt_translations_path: str = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
        if self.qt_translator.load(locale_to_load, "qtbase", "_", qt_translations_path) or \
           self.qt_translator.load(QLocale.system(), "qtbase", "_", qt_translations_path):
            self.installTranslator(self.qt_translator)

    def setup_connections(self) -> None:
        """
        Connects signals from various components to their respective slots
        to enable inter-component communication.
        """
        self.monitor.foreground_changed.connect(
            self.application_identity.on_foreground_changed
        )
        self.monitor.foreground_polled.connect(
            self.game_guard_runtime.on_foreground_polled
        )
        self.application_identity.active_app_changed.connect(
            self.overlay_window.on_active_app_changed
        )
        self.application_identity.active_app_changed.connect(
            self.hud_controller.on_active_app_changed
        )
        self.application_identity.active_app_changed.connect(
            self.current_application_candidate.on_active_app_changed
        )
        self.application_identity.active_app_changed.connect(
            self.game_guard_runtime.on_active_app_changed
        )
        self.game_guard_runtime.suppression_changed.connect(
            self.hud_controller.on_suppression_changed
        )
        self.kb_handler.key_event_signal.connect(self.overlay_window.on_key_event)
        self.kb_handler.key_event_signal.connect(self.hud_controller.on_key_event)
        self.kb_handler.key_event_signal.connect(self._reconcile_win_proxy_state)
        self.kb_handler.modifiers_changed.connect(self.overlay_window.on_modifiers_changed)
        self.kb_handler.modifiers_changed.connect(self.hud_controller.on_modifiers_changed)
        self._win_release_bridge.physical_win_released.connect(
            self.kb_handler.reconcile_win_release,
            type=Qt.ConnectionType.QueuedConnection,
        )
        # self.kb_handler.exit_signal.connect(self.quit_application) # Exit hotkey removed.

    @Slot(str, str)
    def _reconcile_win_proxy_state(
        self,
        key_name: str,
        event_type: str,
    ) -> None:
        """Keep the proxy's native Win session aligned with recovered input."""

        if key_name == "Win" and event_type == "up":
            self.win_discovery_proxy.reconcile_physical_win_state()

    def _initialize_tray_icon_object(self) -> None:
        """
        Initializes the QSystemTrayIcon object itself.
        This method is called once during application startup.
        """
        if self.tray_icon is None: # Ensure creation only once.
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def _update_tray_icon_ui(self) -> None:
        """
        Sets or updates the system tray icon's visual elements (icon, tooltip, context menu).
        This method is called on startup and when UI retranslation is needed.
        The context menu is styled with fixed dark theme colors.
        """
        if self.tray_icon is None:
            # This should not happen if _initialize_tray_icon_object was called correctly.
            print("Error: Tray icon object not initialized prior to UI update.")
            return

        # Set the tray icon image.
        icon_path: str = os.path.join(APP_ROOT_DIR, "assets", "app_icon.png")
        os.makedirs(os.path.join(APP_ROOT_DIR, "assets"), exist_ok=True)
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        else: # Fallback if custom icon is missing.
            self.tray_icon.setIcon(QIcon.fromTheme("input-keyboard", QIcon(":/qt-project.org/styles/commonstyle/images/standardbutton-ok-16.png")))

        # Set the tooltip (this text is translatable).
        self.tray_icon.setToolTip(self.tr("Shortcut Overlay"))

        # Manage the context menu: remove old one if exists, then create and set new one.
        current_menu = self.tray_icon.contextMenu()
        if current_menu:
            current_menu.clear() # Remove all actions.
            current_menu.deleteLater() # Schedule for deletion.
            self.tray_icon.setContextMenu(None) # Disassociate.

        new_menu: QMenu = QMenu(self.overlay_window) # Parented for proper Qt object lifetime.

        # Apply fixed dark styling to the tray menu.
        # Uses color constants defined in SettingsDialog for consistency.
        new_menu.setStyleSheet(f"""
            QMenu {{
                background-color: {SettingsDialog.DIALOG_BACKGROUND_COLOR};
                color: {SettingsDialog.DIALOG_TEXT_COLOR};
                border: 1px solid {SettingsDialog.GROUPBOX_BORDER_COLOR};
            }}
            QMenu::item {{
                padding: 5px 20px 5px 20px; /* top, right, bottom, left padding */
            }}
            QMenu::item:selected {{ /* Hover/selection style */
                background-color: {SettingsDialog.BUTTON_HOVER_BG_COLOR};
            }}
            QMenu::separator {{
                height: 1px;
                background: {SettingsDialog.GROUPBOX_BORDER_COLOR};
                margin-left: 5px;
                margin-right: 5px;
            }}
        """)

        # Create and add actions to the menu (texts are translatable).
        game_mode_action = QAction(self.tr("Game Mode"), new_menu)
        game_mode_action.setCheckable(True)
        game_mode_action.setChecked(
            self.suppression_policy.manual_game_mode_enabled
        )
        game_mode_action.toggled.connect(self.set_game_mode_enabled)
        new_menu.addAction(game_mode_action)
        self.game_mode_action = game_mode_action

        new_menu.addSeparator()

        show_hide_action: QAction = QAction(self.tr("Show/Hide Overlay"), new_menu)
        show_hide_action.triggered.connect(self.toggle_overlay_window)
        new_menu.addAction(show_hide_action)

        settings_action: QAction = QAction(self.tr("Settings..."), new_menu)
        settings_action.triggered.connect(self.open_settings_dialog)
        new_menu.addAction(settings_action)

        about_action: QAction = QAction(self.tr("About..."), new_menu)
        about_action.triggered.connect(self.open_about_dialog)
        new_menu.addAction(about_action)

        new_menu.addSeparator()

        quit_action: QAction = QAction(self.tr("Exit"), new_menu)
        quit_action.triggered.connect(self.quit_application)
        new_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(new_menu)
        
        # Ensure the tray icon is visible.
        if not self.tray_icon.isVisible():
            self.tray_icon.show()

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_tray_icon_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """
        Handles activation events for the system tray icon (e.g., double-click).

        Args:
            reason: Specifies how the tray icon was activated.
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_overlay_window()

    def toggle_overlay_window(self) -> None:
        """
        Toggles the visibility of the main overlay window.
        """
        if self.overlay_window.isVisible():
            self.overlay_window.hide()
        elif self.suppression_policy.allows(PresentationIntent.USER_INITIATED):
            self.overlay_window.show()
            self.overlay_window.activateWindow() # Bring to front.

    @Slot(bool)
    def set_game_mode_enabled(self, enabled: bool) -> None:
        """Apply session-only Manual Game Mode without touching input hooks."""

        self.game_guard_runtime.set_manual_game_mode(enabled)
        if enabled:
            self.overlay_window.hide()

    def open_settings_dialog(self) -> None:
        """
        Opens the application settings dialog.
        The dialog uses its own fixed styling, independent of the overlay theme.
        """
        current_settings: Dict[str, Any] = self.config_mgr.get_all_settings()
        # SettingsDialog constructor no longer needs dialog_text_color passed.
        dialog = SettingsDialog(
            current_settings,
            parent=self.overlay_window,
            current_app_provider=(
                self.current_application_candidate.editable_candidate
            ),
        )
        dialog.settings_changed.connect(self.handle_settings_changed)
        dialog.custom_apps_requested.connect(
            lambda: self.open_user_shortcut_manager_dialog(dialog)
        )
        library_requested = getattr(dialog, "shortcut_library_requested", None)
        if library_requested is not None:
            library_requested.connect(
                lambda: self.open_shortcut_library_dialog(dialog)
            )
        dialog.setWindowModality(Qt.ApplicationModal) # Block interaction with parent.
        dialog.exec() # Show modally.

    def open_user_shortcut_manager_dialog(self, parent=None) -> None:
        """Open the detached USER profile editor from application settings."""

        from scripts.user_shortcut_manager_dialog import UserShortcutManagerDialog

        dialog = UserShortcutManagerDialog(
            self.user_shortcut_store,
            self.current_application_candidate,
            self.apply_user_profiles,
            self.config_mgr.get_all_shortcuts(),
            self.config_mgr.get_setting("language", "en_US"),
            parent=parent or self.overlay_window,
        )
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.exec()

    def open_shortcut_library_dialog(self, parent=None) -> None:
        """Open the Catalog-backed Quick HUD selection Library."""

        from scripts.shortcut_library_dialog import (
            ShortcutLibraryDialog,
            ShortcutLibraryModel,
        )

        model = ShortcutLibraryModel(
            self.config_mgr.get_shortcut_catalog(),
            self.quick_hud_selection_store,
            self.user_shortcut_store.snapshot(),
            self.config_mgr.get_setting("language", "en_US"),
        )
        dialog = ShortcutLibraryDialog(model, parent=parent or self.overlay_window)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.exec()
        self.hud_controller.refresh_current_state()

    def apply_user_profiles(self, snapshot: Mapping[str, object]) -> None:
        """Apply one USER snapshot to presentation, resolution, then refresh."""

        self.shortcut_hud_window.update_application_display_names(
            get_profile_display_names(snapshot)
        )
        self.hud_controller.update_user_profiles(snapshot)

    def handle_settings_changed(self, new_settings: Dict[str, Any]) -> None:
        """
        Callback for when settings are changed in the SettingsDialog.
        Applies new settings to the application, saves them, and reloads
        translatable UI elements if the language setting was modified.

        Args:
            new_settings: A dictionary containing the new application settings.
        """
        old_lang: Optional[str] = self.config_mgr.get_setting("language")
        self.config_mgr.update_settings(new_settings) # Save to file.
        self.game_guard_runtime.update_settings(self.config_mgr.get_all_settings())
        self.overlay_window.apply_current_settings() # Apply to overlay (theme, opacity).
        self.hud_controller.refresh_current_state()

        if old_lang != new_settings.get("language"):
            # Re-initialize translators and load new translation files.
            if not self.translator.isEmpty():
                self.removeTranslator(self.translator)
                self.translator = QTranslator()
            if not self.qt_translator.isEmpty():
                self.removeTranslator(self.qt_translator)
                self.qt_translator = QTranslator()
            self.load_translations()

            # Update UI elements that contain translatable text.
            self._update_tray_icon_ui() # Tray menu and tooltip.
            self.overlay_window.retranslate_ui() # Overlay window content.

    def open_about_dialog(self) -> None:
        """
        Opens the "About" dialog, which displays application information.
        The dialog uses its own fixed styling.
        """
        dialog = AboutDialog(parent=self.overlay_window) # Uses its own fixed styles.
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.exec()

    def quit_application(self) -> None:
        """
        Performs cleanup operations (stops listeners, hides tray icon) and
        quits the Qt application.
        """
        print("Quitting Shortcut Overlay application...")
        self.hud_controller.stop()
        self.application_identity.stop_requests()
        self.application_identity.stop_event_hook()
        if not self.application_identity.stop_worker(timeout=1.0):
            print("Warning: WPS identity worker did not stop within 1 second.")
        self.win_discovery_proxy.stop()
        self.kb_handler.stop_listening()
        self.monitor.stop_monitoring()
        if self.tray_icon:
            self.tray_icon.hide()
            # self.tray_icon.deleteLater() # Optional: schedule for deletion.
        self.quit()


def main() -> None:
    """
    Main entry point for the Shortcut Overlay application.
    Sets up High DPI attributes and runs the QApplication.
    """
    app = ShortcutOverlayApplication(sys.argv)
    exit_code: int = app.exec() # Starts the Qt event loop.
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
