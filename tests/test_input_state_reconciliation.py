from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from scripts.input_state_reconciler import (
    PhysicalModifierReconciler,
    VK_LCONTROL,
    VK_LMENU,
    VK_LSHIFT,
    VK_LWIN,
    VK_RCONTROL,
    VK_RMENU,
    VK_RSHIFT,
    VK_RWIN,
    WindowsPhysicalModifierStateReader,
)
from scripts.keyboard_handler import KeyboardHandler


class _FakeGetAsyncKeyState:
    def __init__(self, pressed_vks=()) -> None:
        self.pressed_vks = set(pressed_vks)
        self.low_bit_only_vks: set[int] = set()
        self.error: Exception | None = None

    def __call__(self, vk: int) -> int:
        if self.error is not None:
            raise self.error
        if vk in self.pressed_vks:
            return 0x8000
        if vk in self.low_bit_only_vks:
            return 0x0001
        return 0


class _HookRaceReconciler:
    def __init__(self) -> None:
        self.on_read = lambda: None

    def reconcile(self, _internal_modifiers, *, only=None) -> set[str]:
        self.on_read()
        return set()


def _make_handler(
    pressed_vks=(),
) -> tuple[KeyboardHandler, _FakeGetAsyncKeyState]:
    physical_state = _FakeGetAsyncKeyState(pressed_vks)
    reader = WindowsPhysicalModifierStateReader(physical_state)
    reconciler = PhysicalModifierReconciler(reader)
    return KeyboardHandler(modifier_reconciler=reconciler), physical_state


def _event(name: str, event_type: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, event_type=event_type)


class PhysicalModifierReconcilerTests(unittest.TestCase):
    def test_reader_distinguishes_every_left_and_right_modifier(self) -> None:
        cases = (
            (VK_LCONTROL, "ctrl"),
            (VK_RCONTROL, "ctrl"),
            (VK_LMENU, "alt"),
            (VK_RMENU, "alt"),
            (VK_LSHIFT, "shift"),
            (VK_RSHIFT, "shift"),
            (VK_LWIN, "win"),
            (VK_RWIN, "win"),
        )

        for vk, expected in cases:
            with self.subTest(vk=vk):
                physical_state = _FakeGetAsyncKeyState({vk})
                reader = WindowsPhysicalModifierStateReader(physical_state)
                self.assertEqual(
                    reader.read_pressed_modifiers(),
                    frozenset({expected}),
                )

    def test_reader_ignores_get_async_key_state_low_bit(self) -> None:
        physical_state = _FakeGetAsyncKeyState()
        physical_state.low_bit_only_vks.update(
            {
                VK_LCONTROL,
                VK_RCONTROL,
                VK_LMENU,
                VK_RMENU,
                VK_LSHIFT,
                VK_RSHIFT,
                VK_LWIN,
                VK_RWIN,
            }
        )

        reader = WindowsPhysicalModifierStateReader(physical_state)

        self.assertEqual(reader.read_pressed_modifiers(), frozenset())

    def test_stale_ctrl_reconciles_to_none(self) -> None:
        reconciler = PhysicalModifierReconciler(
            WindowsPhysicalModifierStateReader(_FakeGetAsyncKeyState())
        )

        self.assertEqual(reconciler.reconcile({"ctrl"}), set())

    def test_stale_ctrl_shift_preserves_physically_held_ctrl(self) -> None:
        physical_state = _FakeGetAsyncKeyState({VK_RCONTROL})
        reconciler = PhysicalModifierReconciler(
            WindowsPhysicalModifierStateReader(physical_state)
        )

        self.assertEqual(
            reconciler.reconcile({"ctrl", "shift"}),
            {"ctrl"},
        )

    def test_reconciliation_never_invents_altgr_ctrl_alt_state(self) -> None:
        physical_state = _FakeGetAsyncKeyState({VK_LCONTROL, VK_RMENU})
        reconciler = PhysicalModifierReconciler(
            WindowsPhysicalModifierStateReader(physical_state)
        )

        self.assertEqual(reconciler.reconcile({"alt"}), {"alt"})
        self.assertEqual(reconciler.reconcile(set()), set())

    def test_reader_failure_preserves_internal_state(self) -> None:
        physical_state = _FakeGetAsyncKeyState()
        physical_state.error = OSError("physical state unavailable")
        reconciler = PhysicalModifierReconciler(
            WindowsPhysicalModifierStateReader(physical_state)
        )

        self.assertEqual(
            reconciler.reconcile({"ctrl", "shift"}),
            {"ctrl", "shift"},
        )


class KeyboardHandlerReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QCoreApplication.instance() or QCoreApplication([])

    def test_normal_ctrl_down_up_behavior_is_unchanged(self) -> None:
        handler, _physical_state = _make_handler()
        key_events: list[tuple[str, str]] = []
        modifier_states: list[set[str]] = []
        handler.key_event_signal.connect(
            lambda key, event_type: key_events.append((key, event_type))
        )
        handler.modifiers_changed.connect(
            lambda modifiers: modifier_states.append(set(modifiers))
        )

        with patch("scripts.keyboard_handler.keyboard.is_pressed", return_value=False):
            handler._key_event_callback(_event("left ctrl", "down"))
            handler._key_event_callback(_event("left ctrl", "up"))

        self.assertEqual(key_events, [("Ctrl", "down"), ("Ctrl", "up")])
        self.assertEqual(modifier_states, [{"ctrl"}, set()])
        self.assertEqual(handler._active_modifiers, set())

    def test_stale_modifier_is_removed_through_handler_signal_chain(self) -> None:
        handler, _physical_state = _make_handler()
        handler._active_modifiers.add("ctrl")
        handler._pressed_keys["Ctrl"] = 1.0
        key_events: list[tuple[str, str]] = []
        modifier_states: list[set[str]] = []
        handler.key_event_signal.connect(
            lambda key, event_type: key_events.append((key, event_type))
        )
        handler.modifiers_changed.connect(
            lambda modifiers: modifier_states.append(set(modifiers))
        )

        handler._check_key_states()

        self.assertEqual(handler._active_modifiers, set())
        self.assertNotIn("Ctrl", handler._pressed_keys)
        self.assertEqual(key_events, [("Ctrl", "up")])
        self.assertEqual(modifier_states, [set()])

    def test_partial_recovery_emits_one_corrected_modifier_state(self) -> None:
        handler, _physical_state = _make_handler({VK_LCONTROL})
        handler._active_modifiers.update({"ctrl", "shift"})
        handler._pressed_keys.update({"Ctrl": 1.0, "Shift": 1.0})
        modifier_states: list[set[str]] = []
        handler.modifiers_changed.connect(
            lambda modifiers: modifier_states.append(set(modifiers))
        )

        handler._check_key_states()

        self.assertEqual(handler._active_modifiers, {"ctrl"})
        self.assertIn("Ctrl", handler._pressed_keys)
        self.assertNotIn("Shift", handler._pressed_keys)
        self.assertEqual(modifier_states, [{"ctrl"}])

    def test_win_release_preserves_other_physical_win_side(self) -> None:
        handler, physical_state = _make_handler({VK_RWIN})
        handler._active_modifiers.add("win")
        modifier_states: list[set[str]] = []
        handler.modifiers_changed.connect(
            lambda modifiers: modifier_states.append(set(modifiers))
        )

        handler.reconcile_win_release(VK_LWIN)
        self.assertEqual(handler._active_modifiers, {"win"})
        self.assertEqual(modifier_states, [])

        physical_state.pressed_vks.clear()
        handler.reconcile_win_release(VK_RWIN)
        self.assertEqual(handler._active_modifiers, set())
        self.assertEqual(modifier_states, [set()])

    def test_newer_hook_event_wins_over_in_flight_physical_snapshot(self) -> None:
        reconciler = _HookRaceReconciler()
        handler = KeyboardHandler(modifier_reconciler=reconciler)
        handler._active_modifiers.add("ctrl")
        handler._pressed_keys["Ctrl"] = 1.0
        reconciler.on_read = lambda: handler._key_event_callback(
            _event("left ctrl", "down")
        )

        handler._reconcile_modifier_state()

        self.assertEqual(handler._active_modifiers, {"ctrl"})
        self.assertIn("Ctrl", handler._pressed_keys)

    def test_listener_is_passive_and_watchdog_stops_when_idle(self) -> None:
        handler, physical_state = _make_handler({VK_LCONTROL})

        with (
            patch("scripts.keyboard_handler.keyboard.hook") as hook,
            patch("scripts.keyboard_handler.keyboard.unhook_all"),
            patch("scripts.keyboard_handler.keyboard.is_pressed", return_value=False),
        ):
            handler.start_listening()
            hook.assert_called_once_with(handler._key_event_callback, suppress=False)
            self.assertFalse(handler._state_check_timer.isActive())

            handler._key_event_callback(_event("c", "down"))
            QCoreApplication.processEvents()
            self.assertFalse(handler._state_check_timer.isActive())
            handler._key_event_callback(_event("c", "up"))

            handler._key_event_callback(_event("left ctrl", "down"))
            QCoreApplication.processEvents()
            self.assertTrue(handler._state_check_timer.isActive())

            physical_state.pressed_vks.clear()
            handler._key_event_callback(_event("left ctrl", "up"))
            QCoreApplication.processEvents()
            self.assertFalse(handler._state_check_timer.isActive())
            handler.stop_listening()

    def test_common_system_shortcut_events_remain_observable(self) -> None:
        cases = (
            ("left ctrl", "c", "Ctrl", "C"),
            ("left ctrl", "v", "Ctrl", "V"),
            ("left ctrl", "s", "Ctrl", "S"),
            ("left alt", "tab", "Alt", "Tab"),
            ("left windows", "r", "Win", "R"),
        )

        for modifier, terminal, normalized_modifier, normalized_terminal in cases:
            with self.subTest(modifier=modifier, terminal=terminal):
                handler, _physical_state = _make_handler()
                key_events: list[tuple[str, str]] = []
                handler.key_event_signal.connect(
                    lambda key, event_type: key_events.append((key, event_type))
                )
                with patch(
                    "scripts.keyboard_handler.keyboard.is_pressed",
                    return_value=False,
                ):
                    handler._key_event_callback(_event(modifier, "down"))
                    handler._key_event_callback(_event(terminal, "down"))
                    handler._key_event_callback(_event(terminal, "up"))
                    handler._key_event_callback(_event(modifier, "up"))

                self.assertEqual(
                    key_events,
                    [
                        (normalized_modifier, "down"),
                        (normalized_terminal, "down"),
                        (normalized_terminal, "up"),
                        (normalized_modifier, "up"),
                    ],
                )


if __name__ == "__main__":
    unittest.main()
