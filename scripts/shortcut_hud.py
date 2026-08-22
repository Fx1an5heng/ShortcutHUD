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

from .shortcut_resolver import ShortcutEntry


MAX_VISIBLE_ENTRIES = 8


def select_description_text(description: object, language: str | None) -> str:
    """Return display text without changing resolver-owned description data."""

    if isinstance(description, str):
        return description
    if not isinstance(description, Mapping):
        return "N/A"

    language_code = (
        language.split("_", 1)[0].casefold()
        if isinstance(language, str) and language
        else "en"
    )
    fallback_codes = [language_code]
    if language_code != "en":
        fallback_codes.append("en")
    if language_code != "zh":
        fallback_codes.append("zh")

    for code in fallback_codes:
        text = description.get(code)
        if isinstance(text, str):
            return text

    for value in description.values():
        if isinstance(value, str):
            return value
    return "N/A"


class ShortcutHudWindow(QWidget):
    """Single-column HUD that never owns shortcut resolution logic."""

    WINDOW_WIDTH = 360
    SCREEN_MARGIN = 20

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
    ) -> None:
        """Replace the current rows while preserving resolver insertion order."""

        self._header_label.setText(
            f"{application_name or 'DEFAULT'} · {modifier_combination}"
        )
        self._clear_entry_rows()

        for entry in entries[:MAX_VISIBLE_ENTRIES]:
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

        self._finalize_size_and_position()
        self._layout_update_timer.start()

    def show_hud(self) -> None:
        """Show without requesting activation or keyboard focus."""

        self._finalize_size_and_position()
        self.show()
        self._layout_update_timer.start()

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