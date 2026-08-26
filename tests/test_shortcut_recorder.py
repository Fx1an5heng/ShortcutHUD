import unittest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from scripts.shortcut_key import normalize_shortcut_key
from scripts.shortcut_recorder import (
    RecordingRejection,
    RecordingState,
    ShortcutRecorder,
)


def key_event(
    key: Qt.Key,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
    *,
    event_type: QEvent.Type = QEvent.Type.KeyPress,
    text: str = "",
    auto_repeat: bool = False,
) -> QKeyEvent:
    return QKeyEvent(event_type, key, modifiers, text, auto_repeat, 1)


class ShortcutRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.recorder = ShortcutRecorder()

    def _record(self, key: Qt.Key, modifiers: Qt.KeyboardModifier) -> tuple[str, str] | None:
        self.recorder.start()
        result = self.recorder.handle_event(key_event(key, modifiers))
        return result.shortcut if result is not None else None

    def test_normal_single_step_combinations(self) -> None:
        cases = (
            (Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier, ("Ctrl", "P")),
            (
                Qt.Key.Key_P,
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier,
                ("Ctrl+Shift", "P"),
            ),
            (Qt.Key.Key_Return, Qt.KeyboardModifier.AltModifier, ("Alt", "Enter")),
            (Qt.Key.Key_F5, Qt.KeyboardModifier.ShiftModifier, ("Shift", "F5")),
            (
                Qt.Key.Key_F5,
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier,
                ("Ctrl+Alt", "F5"),
            ),
        )
        for key, modifiers, expected in cases:
            with self.subTest(key=key, modifiers=modifiers):
                self.assertEqual(self._record(key, modifiers), expected)
                self.assertEqual(self.recorder.state, RecordingState.IDLE)

    def test_modifier_only_waits_for_a_terminal_key(self) -> None:
        self.recorder.start()
        self.assertIsNone(
            self.recorder.handle_event(
                key_event(
                    Qt.Key.Key_Control,
                    Qt.KeyboardModifier.ControlModifier,
                )
            )
        )
        self.assertEqual(self.recorder.state, RecordingState.RECORDING)
        self.recorder.handle_event(
            key_event(
                Qt.Key.Key_Control,
                Qt.KeyboardModifier.ControlModifier,
                event_type=QEvent.Type.KeyRelease,
            )
        )
        result = self.recorder.handle_event(key_event(Qt.Key.Key_F5))
        self.assertEqual(
            result.rejection if result is not None else None,
            RecordingRejection.NO_MODIFIER,
        )
        self.assertEqual(self.recorder.state, RecordingState.RECORDING)

    def test_auto_repeat_does_not_complete_or_repeat(self) -> None:
        self.recorder.start()
        result = self.recorder.handle_event(
            key_event(
                Qt.Key.Key_P,
                Qt.KeyboardModifier.ControlModifier,
                auto_repeat=True,
            )
        )
        self.assertIsNone(result)
        self.assertEqual(self.recorder.state, RecordingState.RECORDING)

    def test_unsupported_win_altgr_and_ctrl_alt_printable_candidates(self) -> None:
        cases = (
            (
                Qt.Key.Key_P,
                Qt.KeyboardModifier.MetaModifier,
                RecordingRejection.WIN,
            ),
            (
                Qt.Key.Key_P,
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier,
                RecordingRejection.CTRL_ALT_PRINTABLE,
            ),
            (
                Qt.Key.Key_AltGr,
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier,
                RecordingRejection.ALTGR,
            ),
        )
        for key, modifiers, expected in cases:
            with self.subTest(key=key):
                self.recorder.start()
                result = self.recorder.handle_event(key_event(key, modifiers))
                self.assertEqual(result.rejection, expected)
                self.assertEqual(self.recorder.state, RecordingState.RECORDING)

    def test_system_reserved_candidates_are_manual_only(self) -> None:
        cases = (
            (Qt.Key.Key_F4, Qt.KeyboardModifier.AltModifier),
            (
                Qt.Key.Key_Escape,
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier,
            ),
        )
        for key, modifiers in cases:
            with self.subTest(key=key):
                self.recorder.start()
                result = self.recorder.handle_event(key_event(key, modifiers))
                self.assertEqual(
                    result.rejection if result is not None else None,
                    RecordingRejection.UNSUPPORTED_KEY,
                )
                self.assertEqual(self.recorder.state, RecordingState.RECORDING)

    def test_shifted_slash_uses_existing_logical_symbol_identity(self) -> None:
        result = self._record(
            Qt.Key.Key_Question,
            Qt.KeyboardModifier.ShiftModifier,
        )
        self.assertEqual(result, ("Shift", "?"))
        self.assertEqual(result[1], normalize_shortcut_key("?"))

    def test_cancel_clears_state_without_a_persistent_listener(self) -> None:
        self.recorder.start()
        self.recorder.handle_event(
            key_event(Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier)
        )
        self.recorder.cancel()
        self.assertEqual(self.recorder.state, RecordingState.IDLE)
        self.assertEqual(self.recorder.active_modifiers, frozenset())


if __name__ == "__main__":
    unittest.main()
