"""Compact, passive ShortcutHUD presentation window."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import win32con
import win32gui
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .application_display_names import get_application_display_name
from .hud_entry_limits import get_hud_entry_limit
from .shortcut_description import select_description_text
from .shortcut_resolver import ShortcutEntry

def select_visible_entry_groups(
    entries: Sequence[ShortcutEntry],
    local_limit: int,
) -> tuple[list[ShortcutEntry], list[ShortcutEntry]]:
    """Return USER rows plus limited built-ins and all surviving GLOBAL rows.

    Resolver order and conflict ownership are already settled before this
    presentation boundary. Every surviving USER_APP row remains visible.
    APP/DEFAULT rows use the app-specific local budget independently, while
    GLOBAL rows remain pinned after local content and never consume that budget.
    """

    user_entries = [entry for entry in entries if entry.source == "USER_APP"]
    built_in_entries = [
        entry for entry in entries if entry.source in {"APP", "DEFAULT"}
    ][:max(0, local_limit)]
    global_entries = [
        entry for entry in entries if entry.source == "GLOBAL"
    ]
    return user_entries + built_in_entries, global_entries


class ShortcutHudWindow(QWidget):
    """Single-column HUD that never owns shortcut resolution logic."""

    WINDOW_WIDTH = 360
    SCREEN_MARGIN = 20

    def __init__(
        self,
        parent: QWidget | None = None,
        application_display_names: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._user_display_names = self._normalize_display_names(
            application_display_names
        )
        self.setObjectName("shortcutHudWindow")
        self.setWindowTitle("ShortcutHUD")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedWidth(self.WINDOW_WIDTH)

        self._layout_update_timer = QTimer(self)
        self._layout_update_timer.setSingleShot(True)
        self._layout_update_timer.setInterval(0)
        self._layout_update_timer.timeout.connect(
            self._finalize_size_and_position
        )

        outer_layout = QVBoxLayout(self)
        self._outer_layout = outer_layout
        outer_layout.setContentsMargins(0, 0, 0, 0)

        panel = QWidget(self)
        panel.setObjectName("shortcutHudPanel")
        panel_layout = QVBoxLayout(panel)
        self._panel_layout = panel_layout
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(8)

        self._header_label = QLabel(panel)
        self._header_label.setObjectName("shortcutHudHeader")
        self._header_label.setFocusPolicy(Qt.NoFocus)
        panel_layout.addWidget(self._header_label)

        separator = QFrame(panel)
        separator.setObjectName("shortcutHudSeparator")
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        panel_layout.addWidget(separator)

        self._entries_container = QWidget(panel)
        self._entries_layout = QVBoxLayout(self._entries_container)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(5)
        panel_layout.addWidget(self._entries_container)

        outer_layout.addWidget(panel)
        self.setStyleSheet(
            """
            QWidget#shortcutHudPanel {
                background-color: rgba(24, 26, 34, 232);
                border: 1px solid rgba(130, 140, 165, 150);
                border-radius: 8px;
            }
            QLabel#shortcutHudHeader {
                color: #F4F6FA;
                font-size: 12pt;
                font-weight: 600;
                background: transparent;
            }
            QFrame#shortcutHudSeparator {
                background-color: rgba(130, 140, 165, 110);
                border: none;
            }
            QWidget#shortcutHudGlobalSection {
                background: transparent;
            }
            QLabel#shortcutHudGlobalSectionLabel {
                color: rgba(190, 198, 215, 190);
                font-size: 8pt;
                font-weight: 500;
                background: transparent;
            }
            QFrame#shortcutHudGlobalSectionLine {
                background-color: rgba(130, 140, 165, 80);
                border: none;
            }
            QLabel#shortcutHudKey {
                color: #9CC9FF;
                font-size: 10pt;
                font-weight: 700;
                background: transparent;
            }
            QLabel#shortcutHudDescription {
                color: #E6E9F0;
                font-size: 10pt;
                background: transparent;
            }
            """
        )

    def set_entries(
        self,
        application_name: str,
        modifier_combination: str,
        entries: Sequence[ShortcutEntry],
        language: str | None,
        application_display_name: str | None = None,
    ) -> None:
        """Replace the current rows while preserving resolver insertion order."""

        entry_limit = get_hud_entry_limit(application_name, modifier_combination)
        local_entries, global_entries = select_visible_entry_groups(
            entries,
            entry_limit,
        )
        display_name = (
            application_display_name
            or get_application_display_name(application_name, self._user_display_names)
            if local_entries
            else None
        )
        header_text = (
            f"{display_name} · {modifier_combination}"
            if display_name
            else modifier_combination
        )
        self._header_label.setText(header_text)
        self._clear_entry_rows()

        for entry in local_entries:
            self._add_entry_row(entry, language)
        if local_entries and global_entries:
            self._add_global_section()
        for entry in global_entries:
            self._add_entry_row(entry, language)

        self._finalize_size_and_position()
        self._layout_update_timer.start()

    def _add_entry_row(
        self,
        entry: ShortcutEntry,
        language: str | None,
    ) -> None:
        row = QWidget(self._entries_container)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        key_label = QLabel(entry.key, row)
        key_label.setObjectName("shortcutHudKey")
        key_label.setFixedWidth(76)
        key_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        key_label.setFocusPolicy(Qt.NoFocus)

        description_text = select_description_text(entry.description, language)
        description_label = QLabel(description_text, row)
        description_label.setObjectName("shortcutHudDescription")
        description_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        description_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        description_label.setToolTip(description_text)
        description_label.setFocusPolicy(Qt.NoFocus)

        row_layout.addWidget(key_label)
        row_layout.addWidget(description_label, 1)
        self._entries_layout.addWidget(row)

    def _add_global_section(self) -> None:
        section = QWidget(self._entries_container)
        section.setObjectName("shortcutHudGlobalSection")
        section_layout = QHBoxLayout(section)
        section_layout.setContentsMargins(0, 3, 0, 1)
        section_layout.setSpacing(8)

        label = QLabel("全局", section)
        label.setObjectName("shortcutHudGlobalSectionLabel")
        label.setFocusPolicy(Qt.NoFocus)

        line = QFrame(section)
        line.setObjectName("shortcutHudGlobalSectionLine")
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)

        section_layout.addWidget(label)
        section_layout.addWidget(line, 1)
        self._entries_layout.addWidget(section)

    def show_hud(self) -> None:
        """Show without requesting activation or keyboard focus."""

        self._finalize_size_and_position()
        self.show()
        self._layout_update_timer.start()

    def update_application_display_names(
        self,
        display_names: Mapping[str, str] | None,
    ) -> None:
        """Replace presentation-only user labels for a future editor reload."""

        self._user_display_names = self._normalize_display_names(display_names)

    def _clear_entry_rows(self) -> None:
        while self._entries_layout.count():
            item = self._entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _finalize_size_and_position(self) -> None:
        self._entries_layout.invalidate()
        self._entries_layout.activate()
        self._entries_container.adjustSize()
        self._panel_layout.invalidate()
        self._panel_layout.activate()
        self._outer_layout.invalidate()
        self._outer_layout.activate()
        target_height = self._outer_layout.totalSizeHint().height()
        self.resize(self.width(), target_height)
        self._position_bottom_right()

    def _position_bottom_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        x = max(
            available.x(),
            available.x() + available.width() - self.width() - self.SCREEN_MARGIN,
        )
        y = max(
            available.y(),
            available.y() + available.height() - self.height() - self.SCREEN_MARGIN,
        )
        self.move(x, y)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._apply_windows_styles()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self._position_bottom_right()

    def _apply_windows_styles(self) -> None:
        """Apply layered/no-activate styles without mouse click-through."""

        hwnd = int(self.winId())
        if not hwnd:
            return
        try:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(
                hwnd,
                win32con.GWL_EXSTYLE,
                style | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE,
            )
        except Exception as error:
            print(f"Error setting ShortcutHUD Win32 window styles: {error}")

    @staticmethod
    def _normalize_display_names(
        display_names: Mapping[str, str] | None,
    ) -> dict[str, str]:
        if not isinstance(display_names, Mapping):
            return {}
        return {
            app_id.strip().upper(): display_name.strip()
            for app_id, display_name in display_names.items()
            if isinstance(app_id, str)
            and app_id.strip()
            and isinstance(display_name, str)
            and display_name.strip()
        }
