r"""Local Qt shortcut-capture probe for Context-free Recorder research.

This is an independent development/diagnostic tool, not the ShortcutHUD
product recorder. It never installs a global hook, suppresses system input,
writes configuration, or stores an input history. Only events delivered to
this focused probe window while the user explicitly records are inspected.

Run from the repository root with:

    .\.venv\Scripts\python.exe -B tools\shortcut_recorder_probe.py

Use ``--self-test`` for deterministic state and mapping checks without showing
the interactive probe.
"""

from __future__ import annotations

import argparse
from enum import Enum, auto
from pathlib import Path
import sys
from typing import Final

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.modifier_state import canonicalize_modifier_state
from scripts.shortcut_key import ShortcutKeyError, normalize_shortcut_key


class RecordingState(Enum):
    IDLE = auto()
    RECORDING = auto()
    COMPLETED = auto()


def _enum_value(value: object) -> int:
    enum_value = getattr(value, "value", value)
    return int(enum_value)


_MODIFIER_KEYS: Final[dict[int, str]] = {
    _enum_value(Qt.Key.Key_Control): "Ctrl",
    _enum_value(Qt.Key.Key_Shift): "Shift",
    _enum_value(Qt.Key.Key_Alt): "Alt",
    _enum_value(Qt.Key.Key_Meta): "Win",
    _enum_value(Qt.Key.Key_AltGr): "AltGr",
}

_SPECIAL_KEYS: Final[dict[int, str]] = {
    _enum_value(Qt.Key.Key_Tab): "Tab",
    _enum_value(Qt.Key.Key_Return): "Enter",
    _enum_value(Qt.Key.Key_Enter): "Enter",
    _enum_value(Qt.Key.Key_Escape): "Esc",
    _enum_value(Qt.Key.Key_Space): "Space",
    _enum_value(Qt.Key.Key_Backspace): "Backspace",
    _enum_value(Qt.Key.Key_Delete): "Delete",
    _enum_value(Qt.Key.Key_Insert): "Insert",
    _enum_value(Qt.Key.Key_Home): "Home",
    _enum_value(Qt.Key.Key_End): "End",
    _enum_value(Qt.Key.Key_PageUp): "PageUp",
    _enum_value(Qt.Key.Key_PageDown): "PageDown",
    _enum_value(Qt.Key.Key_Up): "Up",
    _enum_value(Qt.Key.Key_Down): "Down",
    _enum_value(Qt.Key.Key_Left): "Left",
    _enum_value(Qt.Key.Key_Right): "Right",
}

_F1 = _enum_value(Qt.Key.Key_F1)
_F24 = _enum_value(Qt.Key.Key_F24)
_KEY_UNKNOWN = _enum_value(Qt.Key.Key_unknown)


def modifier_name(event: QKeyEvent) -> str | None:
    """Return the existing ShortcutHUD canonical modifier combination."""

    modifiers = event.modifiers()
    tokens: list[str] = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        tokens.append("Ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        tokens.append("Alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        tokens.append("Shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        tokens.append("Win")
    return canonicalize_modifier_state(tokens)


def is_explicit_altgr(event: QKeyEvent) -> bool:
    """Detect only AltGr representations Qt exposes unambiguously.

    Qt may expose AltGr as ordinary Ctrl+Alt on Windows, depending on the
    active keyboard layout. That ambiguous representation cannot be safely
    distinguished here and is an explicit limitation of this local probe.
    """

    if event.key() == _enum_value(Qt.Key.Key_AltGr):
        return True
    return bool(event.modifiers() & Qt.KeyboardModifier.GroupSwitchModifier)


def terminal_key_name(event: QKeyEvent) -> str | None:
    """Map QKeyEvent.key(), never text(), into the existing key validator."""

    key = event.key()
    if key in _MODIFIER_KEYS or key in (0, _KEY_UNKNOWN):
        return None
    if key in _SPECIAL_KEYS:
        candidate = _SPECIAL_KEYS[key]
    elif _F1 <= key <= _F24:
        candidate = f"F{key - _F1 + 1}"
    elif ord("A") <= key <= ord("Z"):
        candidate = chr(key)
    elif ord("0") <= key <= ord("9"):
        candidate = chr(key)
    elif 0x20 <= key <= 0x7E:
        candidate = chr(key)
    else:
        return None

    try:
        return normalize_shortcut_key(candidate)
    except ShortcutKeyError:
        return None


def describe_event(event: QKeyEvent) -> str:
    """Format only the current event; no event history is retained."""

    event_type = QEvent.Type(event.type()).name
    return (
        f"type={event_type} qt_key=0x{event.key():X} "
        f"native_vk=0x{event.nativeVirtualKey():X} "
        f"native_scan=0x{event.nativeScanCode():X} "
        f"native_modifiers=0x{event.nativeModifiers():X} "
        f"qt_modifiers=0x{_enum_value(event.modifiers()):X} "
        f"auto_repeat={event.isAutoRepeat()} text={event.text()!r}"
    )


class ShortcutRecorderProbe(QWidget):
    """Focused-window recorder spike with no global or persistent state."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Shortcut Recorder Capture Probe — Development Tool")
        self.setMinimumWidth(720)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.state = RecordingState.IDLE
        self.result: tuple[str, str] | None = None
        self._altgr_active = False
        self._filtered_objects: list[QWidget] = []

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Local Qt diagnostic only. Click Start Recording, then press one "
            "modifier combination plus one keyboard key. Mouse buttons and "
            "unmodified keys are intentionally unsupported."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        self.record_button = QPushButton("Start Recording", self)
        self.record_button.clicked.connect(self.toggle_recording)
        layout.addWidget(self.record_button)

        form = QFormLayout()
        self.state_label = QLabel("IDLE", self)
        self.status_label = QLabel("Ready", self)
        self.event_label = QLabel("—", self)
        self.event_label.setWordWrap(True)
        self.modifier_label = QLabel("—", self)
        self.key_label = QLabel("—", self)
        self.result_label = QLabel("—", self)
        form.addRow("State", self.state_label)
        form.addRow("Status", self.status_label)
        form.addRow("Current event", self.event_label)
        form.addRow("Canonical modifier", self.modifier_label)
        form.addRow("Canonical key", self.key_label)
        form.addRow("Canonical result", self.result_label)
        layout.addLayout(form)

    def toggle_recording(self) -> None:
        if self.state is RecordingState.RECORDING:
            self.cancel_recording("Cancelled explicitly")
        else:
            self.begin_recording()

    def begin_recording(self) -> None:
        self._remove_local_filters()
        self.state = RecordingState.RECORDING
        self.result = None
        self._altgr_active = False
        self.state_label.setText("RECORDING")
        self.status_label.setText("Press modifiers plus one keyboard key")
        self.event_label.setText("—")
        self.modifier_label.setText("—")
        self.key_label.setText("—")
        self.result_label.setText("—")
        self.record_button.setText("Cancel Recording")
        self._install_local_filters()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def cancel_recording(self, reason: str) -> None:
        if self.state is not RecordingState.RECORDING:
            return
        self._remove_local_filters()
        self.state = RecordingState.IDLE
        self._altgr_active = False
        self.state_label.setText("IDLE")
        self.status_label.setText(reason)
        self.record_button.setText("Start Recording")

    def _complete(self, modifier: str, key: str) -> None:
        self._remove_local_filters()
        self.state = RecordingState.COMPLETED
        self.result = (modifier, key)
        self.state_label.setText("COMPLETED")
        self.status_label.setText("Captured one single-step shortcut")
        self.modifier_label.setText(modifier)
        self.key_label.setText(key)
        self.result_label.setText(f"{modifier} + {key}")
        self.record_button.setText("Start Recording")

    def _install_local_filters(self) -> None:
        objects = [self, *self.findChildren(QWidget)]
        for widget in objects:
            widget.installEventFilter(self)
        self._filtered_objects = objects

    def _remove_local_filters(self) -> None:
        for widget in self._filtered_objects:
            widget.removeEventFilter(self)
        self._filtered_objects.clear()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if self.state is not RecordingState.RECORDING:
            return False
        if watched not in self._filtered_objects:
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if event.type() == QEvent.Type.KeyPress:
            self._handle_key_press(event)
            return True
        if event.type() == QEvent.Type.KeyRelease:
            self._handle_key_release(event)
            return True
        return False

    def _handle_key_press(self, event: QKeyEvent) -> None:
        event_description = describe_event(event)
        self.event_label.setText(event_description)
        print(event_description, flush=True)

        if event.isAutoRepeat():
            self.status_label.setText("Ignored auto-repeat")
            return
        if is_explicit_altgr(event):
            self._altgr_active = True
            self.status_label.setText("AltGr is ambiguous and unsupported")
            self.modifier_label.setText("UNSUPPORTED: AltGr")
            return

        modifier_key = _MODIFIER_KEYS.get(event.key())
        if modifier_key is not None:
            if modifier_key == "AltGr":
                self._altgr_active = True
                self.status_label.setText("AltGr is ambiguous and unsupported")
                self.modifier_label.setText("UNSUPPORTED: AltGr")
            else:
                self.modifier_label.setText(modifier_name(event) or modifier_key)
                self.status_label.setText("Modifier captured; waiting for a key")
            return

        if self._altgr_active:
            self.status_label.setText("Ignored key while AltGr is active")
            return

        modifier = modifier_name(event)
        if modifier is None:
            self.status_label.setText("A modifier is required in this version")
            return

        key = terminal_key_name(event)
        if key is None:
            self.status_label.setText("Unsupported or unknown terminal key")
            return

        self._complete(modifier, key)

    def _handle_key_release(self, event: QKeyEvent) -> None:
        event_description = describe_event(event)
        self.event_label.setText(event_description)
        print(event_description, flush=True)
        if event.key() == _enum_value(Qt.Key.Key_AltGr):
            self._altgr_active = False

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and self.state is RecordingState.RECORDING
        ):
            QTimer.singleShot(
                0,
                lambda: self.cancel_recording("Cancelled because focus was lost"),
            )
        return handled

    def closeEvent(self, event: QCloseEvent) -> None:
        self.cancel_recording("Cancelled because the probe closed")
        self._remove_local_filters()
        event.accept()


def _key_event(
    key: Qt.Key,
    modifiers: Qt.KeyboardModifier,
    *,
    text: str = "",
    auto_repeat: bool = False,
) -> QKeyEvent:
    return QKeyEvent(
        QEvent.Type.KeyPress,
        key,
        modifiers,
        text,
        auto_repeat,
        1,
    )


def run_self_test() -> int:
    app = QApplication.instance() or QApplication([])
    probe = ShortcutRecorderProbe()

    probe.begin_recording()
    probe._handle_key_press(
        _key_event(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
    )
    assert probe.state is RecordingState.RECORDING
    probe._handle_key_press(
        _key_event(Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier, text="p")
    )
    assert probe.result == ("Ctrl", "P")

    probe.begin_recording()
    probe._handle_key_press(
        _key_event(
            Qt.Key.Key_P,
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.ShiftModifier,
            text="P",
        )
    )
    assert probe.result == ("Ctrl+Shift", "P")

    probe.begin_recording()
    probe._handle_key_press(
        _key_event(
            Qt.Key.Key_Question,
            Qt.KeyboardModifier.ShiftModifier,
            text="?",
        )
    )
    assert probe.result == ("Shift", "?")

    probe.begin_recording()
    probe._handle_key_press(
        _key_event(
            Qt.Key.Key_F24,
            Qt.KeyboardModifier.AltModifier,
        )
    )
    assert probe.result == ("Alt", "F24")

    probe.begin_recording()
    probe._handle_key_press(
        _key_event(
            Qt.Key.Key_P,
            Qt.KeyboardModifier.ControlModifier,
            text="p",
            auto_repeat=True,
        )
    )
    assert probe.state is RecordingState.RECORDING
    assert probe.result is None

    probe._handle_key_press(
        _key_event(Qt.Key.Key_P, Qt.KeyboardModifier.NoModifier, text="p")
    )
    assert probe.state is RecordingState.RECORDING
    assert probe.result is None

    probe._handle_key_press(
        _key_event(
            Qt.Key.Key_AltGr,
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier,
        )
    )
    assert probe.state is RecordingState.RECORDING
    assert probe.result is None
    assert probe._altgr_active

    probe.cancel_recording("Self-test cleanup")
    assert probe.state is RecordingState.IDLE
    assert probe._filtered_objects == []

    expected_terminal_keys = {
        Qt.Key.Key_F1: "F1",
        Qt.Key.Key_F5: "F5",
        Qt.Key.Key_F12: "F12",
        Qt.Key.Key_F13: "F13",
        Qt.Key.Key_F24: "F24",
        Qt.Key.Key_Tab: "Tab",
        Qt.Key.Key_Return: "Enter",
        Qt.Key.Key_Escape: "Esc",
        Qt.Key.Key_Space: "Space",
        Qt.Key.Key_Backspace: "Backspace",
        Qt.Key.Key_Delete: "Delete",
        Qt.Key.Key_Insert: "Insert",
        Qt.Key.Key_Home: "Home",
        Qt.Key.Key_End: "End",
        Qt.Key.Key_PageUp: "PageUp",
        Qt.Key.Key_PageDown: "PageDown",
        Qt.Key.Key_Up: "Up",
        Qt.Key.Key_Down: "Down",
        Qt.Key.Key_Left: "Left",
        Qt.Key.Key_Right: "Right",
    }
    for qt_key, expected in expected_terminal_keys.items():
        event = _key_event(qt_key, Qt.KeyboardModifier.ControlModifier)
        assert terminal_key_name(event) == expected

    for symbol in "`-=[]\\;',./~_+{}|:\"<>?!@#$%^&*()":
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            ord(symbol),
            Qt.KeyboardModifier.ControlModifier,
            "ignored composition text",
            False,
            1,
        )
        assert terminal_key_name(event) == symbol

    probe.begin_recording()
    QApplication.sendEvent(probe, QEvent(QEvent.Type.WindowDeactivate))
    app.processEvents()
    assert probe.state is RecordingState.IDLE
    assert probe.status_label.text() == "Cancelled because focus was lost"
    assert probe._filtered_objects == []

    probe.close()
    app.processEvents()
    print("SELF_TEST_PASS", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic mapping/state checks and exit",
    )
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()

    app = QApplication(sys.argv)
    probe = ShortcutRecorderProbe()
    probe.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
