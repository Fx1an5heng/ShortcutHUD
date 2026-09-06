from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QTranslator, Qt
from PySide6.QtWidgets import QApplication, QWidget

from main import ShortcutOverlayApplication
from scripts.suppression_policy import SuppressionDecision, SuppressionPolicy


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def emit(self) -> None:
        for callback in self._callbacks:
            callback()


class _FakeSettingsDialog:
    last_instance = None

    def __init__(self, settings, parent=None, current_app_provider=None) -> None:
        self.settings = settings
        self.parent = parent
        self.current_app_provider = current_app_provider
        self.settings_changed = _FakeSignal()
        self.custom_apps_requested = _FakeSignal()
        self.modality = None
        _FakeSettingsDialog.last_instance = self

    def setWindowModality(self, modality) -> None:
        self.modality = modality

    def exec(self) -> None:
        self.custom_apps_requested.emit()


class _FakeTrayIcon:
    def __init__(self) -> None:
        self._menu = None

    def setIcon(self, _icon) -> None:
        pass

    def setToolTip(self, _tooltip) -> None:
        pass

    def contextMenu(self):
        return self._menu

    def setContextMenu(self, menu) -> None:
        self._menu = menu

    def isVisible(self) -> bool:
        return True

    def show(self) -> None:
        pass


class ShortcutManagerEntryWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def test_settings_request_calls_shortcut_center_entry_point(self) -> None:
        opened = []
        application = SimpleNamespace(
            config_mgr=SimpleNamespace(get_all_settings=lambda: {"language": "en_US"}),
            overlay_window=object(),
            current_application_candidate=SimpleNamespace(
                editable_candidate=lambda: "CODE.EXE"
            ),
            handle_settings_changed=lambda _settings: None,
            open_shortcut_center_dialog=lambda parent=None: opened.append(parent),
        )

        with patch("main.SettingsDialog", _FakeSettingsDialog):
            ShortcutOverlayApplication.open_settings_dialog(application)

        dialog = _FakeSettingsDialog.last_instance
        self.assertEqual(opened, [dialog])
        self.assertEqual(dialog.modality, Qt.ApplicationModal)
        self.assertEqual(dialog.current_app_provider(), "CODE.EXE")

    def test_new_entry_constructs_user_shortcut_manager_dialog(self) -> None:
        store = object()
        candidate = object()
        parent = object()
        apply_profiles = Mock()
        builtin_shortcuts = {"CODE.EXE": {}}
        config_manager = SimpleNamespace(
            get_all_shortcuts=lambda: builtin_shortcuts,
            get_setting=lambda _name, _default: "en_US",
        )
        application = SimpleNamespace(
            user_shortcut_store=store,
            current_application_candidate=candidate,
            apply_user_profiles=apply_profiles,
            config_mgr=config_manager,
            overlay_window=object(),
        )

        with patch(
            "scripts.user_shortcut_manager_dialog.UserShortcutManagerDialog"
        ) as manager_class:
            ShortcutOverlayApplication.open_user_shortcut_manager_dialog(
                application,
                parent,
            )

        manager_class.assert_called_once_with(
            store,
            candidate,
            apply_profiles,
            builtin_shortcuts,
            "en_US",
            parent=parent,
        )
        manager = manager_class.return_value
        manager.setWindowModality.assert_called_once_with(Qt.ApplicationModal)
        manager.exec.assert_called_once_with()

    def test_tray_has_no_direct_shortcut_manager_or_legacy_entry(self) -> None:
        overlay_window = QWidget()
        self.addCleanup(overlay_window.close)
        tray_icon = _FakeTrayIcon()
        no_op = lambda: None
        application = SimpleNamespace(
            tray_icon=tray_icon,
            overlay_window=overlay_window,
            suppression_policy=SuppressionPolicy(),
            game_mode_action=None,
            tr=lambda text: text,
            set_game_mode_enabled=lambda _enabled: None,
            toggle_overlay_window=no_op,
            open_settings_dialog=no_op,
            open_about_dialog=no_op,
            quit_application=no_op,
        )

        ShortcutOverlayApplication._update_tray_icon_ui(application)

        action_texts = [action.text() for action in tray_icon.contextMenu().actions()]
        self.assertNotIn("Manage Shortcuts...", action_texts)
        self.assertIn("Game Mode", action_texts)
        self.assertIn("Settings...", action_texts)
        self.assertIn("About...", action_texts)
        self.assertTrue(application.game_mode_action.isCheckable())
        self.assertFalse(application.game_mode_action.isChecked())
        self.assertFalse(
            hasattr(ShortcutOverlayApplication, "open_shortcut_manager_dialog")
        )

    def test_game_mode_action_reflects_session_state_after_menu_rebuild(self) -> None:
        overlay_window = QWidget()
        self.addCleanup(overlay_window.close)
        policy = SuppressionPolicy()
        policy.set_manual_game_mode(True)
        application = SimpleNamespace(
            tray_icon=_FakeTrayIcon(),
            overlay_window=overlay_window,
            suppression_policy=policy,
            game_mode_action=None,
            tr=lambda text: text,
            set_game_mode_enabled=lambda _enabled: None,
            toggle_overlay_window=lambda: None,
            open_settings_dialog=lambda: None,
            open_about_dialog=lambda: None,
            quit_application=lambda: None,
        )

        ShortcutOverlayApplication._update_tray_icon_ui(application)

        self.assertTrue(application.game_mode_action.isChecked())

    def test_game_mode_toggle_updates_policy_hides_surfaces_and_notifies_hud(self) -> None:
        overlay_window = QWidget()
        overlay_window.show()
        self.addCleanup(overlay_window.close)
        hud_controller = Mock()
        policy = SuppressionPolicy()
        game_guard_runtime = Mock()

        def set_manual_game_mode(enabled: bool) -> None:
            policy.set_manual_game_mode(enabled)
            hud_controller.on_suppression_changed()

        game_guard_runtime.set_manual_game_mode.side_effect = set_manual_game_mode
        application = SimpleNamespace(
            suppression_policy=policy,
            game_guard_runtime=game_guard_runtime,
            overlay_window=overlay_window,
            hud_controller=hud_controller,
        )

        ShortcutOverlayApplication.set_game_mode_enabled(application, True)

        self.assertIs(
            application.suppression_policy.decision,
            SuppressionDecision.HARD_BLOCK,
        )
        self.assertFalse(overlay_window.isVisible())
        game_guard_runtime.set_manual_game_mode.assert_called_once_with(True)
        hud_controller.on_suppression_changed.assert_called_once_with()

        ShortcutOverlayApplication.set_game_mode_enabled(application, False)

        self.assertIs(
            application.suppression_policy.decision,
            SuppressionDecision.ALLOW,
        )
        self.assertEqual(hud_controller.on_suppression_changed.call_count, 2)

    def test_game_mode_has_compiled_chinese_translation(self) -> None:
        translator = QTranslator()
        self.assertTrue(
            translator.load("i18n/shortcut_overlay_zh_CN.qm")
        )

        self.qt_application.installTranslator(translator)
        try:
            translated = self.qt_application.translate(
                "ShortcutOverlayApplication",
                "Game Mode",
            )
        finally:
            self.qt_application.removeTranslator(translator)

        self.assertEqual(translated, "游戏模式")


if __name__ == "__main__":
    unittest.main()
