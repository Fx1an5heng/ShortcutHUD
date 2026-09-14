"""Cumulative Guide modifier filters and session-scoped Win ownership."""
from dataclasses import replace
import unittest

from scripts.full_guide_input import (
    ModifierTapInterpreter, WindowsGuideWinInputBackend,
    VK_LWIN,
)
from scripts.full_guide_model import ModifierFilterState, group_entries
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import resolve_catalog_view
from tests.test_full_guide_data import entry


class ModifierFilterModelTests(unittest.TestCase):
    def test_cumulative_state_is_canonical_and_duplicate_is_noop(self):
        state = ModifierFilterState().add("Shift").add("Ctrl")
        self.assertEqual(state.selected, ("Ctrl", "Shift"))
        self.assertIs(state.add("Ctrl"), state)
        self.assertEqual(ModifierFilterState().add("Ctrl").add("Alt").selected, ("Ctrl", "Alt"))

    def test_first_stroke_filtering_composes_with_text_search(self):
        rows = resolve_catalog_view(ShortcutCatalog([
            entry("plain", ("Ctrl", "P"), description={"en": "Open", "zh_CN": "打开"}),
            entry("shifted", ("Ctrl", "Shift", "P"), description={"en": "Command", "zh_CN": "命令"}),
            entry("sequence", ("Ctrl+K", "Ctrl+S"), kind="sequence", description={"en": "Keys", "zh_CN": "按键"}),
            entry("single", ("F5",), kind="single"),
            entry("win", ("Win", "E")),
            entry("win-shift", ("Win", "Shift", "S")),
        ]), "SAMPLE.EXE", language="zh_CN")
        self.assertEqual({row.entry.id for section in group_entries(rows, modifiers=("Ctrl",)) for row in section.rows}, {"plain", "shifted", "sequence"})
        self.assertEqual({row.entry.id for section in group_entries(rows, modifiers=("Ctrl", "Shift")) for row in section.rows}, {"shifted"})
        self.assertEqual({row.entry.id for section in group_entries(rows, modifiers=("Win",)) for row in section.rows}, {"win", "win-shift"})
        self.assertEqual({row.entry.id for section in group_entries(rows, modifiers=("Win", "Shift")) for row in section.rows}, {"win-shift"})
        self.assertEqual([row.entry.id for section in group_entries(rows, "命令", ("Ctrl",)) for row in section.rows], ["shifted"])
        self.assertEqual([row.entry.id for section in group_entries(rows, "command", ("Ctrl",)) for row in section.rows], ["shifted"])


class ModifierTapInterpreterTests(unittest.TestCase):
    def test_tap_emits_on_release_but_activation_release_does_not(self):
        model = ModifierTapInterpreter()
        self.assertIsNone(model.handle("Ctrl", "up"))
        self.assertIsNone(model.handle("Ctrl", "down"))
        self.assertEqual(model.handle("Ctrl", "up"), "Ctrl")

    def test_terminal_key_cancels_modifier_taps_including_altgr_shape(self):
        model = ModifierTapInterpreter()
        model.handle("Ctrl", "down")
        model.handle("Alt", "down")
        model.handle("", "down")
        self.assertIsNone(model.handle("Alt", "up"))
        self.assertIsNone(model.handle("Ctrl", "up"))


class GuideWinOwnershipTests(unittest.TestCase):
    def make(self):
        events = []
        backend = WindowsGuideWinInputBackend(lambda *event: events.append(event), foreground_provider=lambda: 100)
        backend.activate(100)
        return backend, events

    def test_active_focused_win_tap_is_suppressed_and_reported(self):
        backend, events = self.make()
        self.assertTrue(backend.process_event(VK_LWIN, "down"))
        self.assertTrue(backend.process_event(VK_LWIN, "up"))
        self.assertEqual(events, [("Win", "down"), ("Win", "up")])

    def test_win_e_is_fully_owned_and_cancels_tap(self):
        backend, events = self.make()
        for vk, action in ((VK_LWIN, "down"), (ord("E"), "down"), (ord("E"), "up"), (VK_LWIN, "up")):
            self.assertTrue(backend.process_event(vk, action))
        interpreter = ModifierTapInterpreter()
        self.assertEqual([interpreter.handle(*event) for event in events], [None, None, None])

    def test_win_shift_reports_both_modifiers(self):
        backend, events = self.make()
        for vk, action in ((VK_LWIN, "down"), (0xA0, "down"), (0xA0, "up"), (VK_LWIN, "up")):
            self.assertTrue(backend.process_event(vk, action))
        interpreter = ModifierTapInterpreter()
        taps = [tap for event in events if (tap := interpreter.handle(*event))]
        self.assertEqual(set(taps), {"Win", "Shift"})

    def test_closed_unfocused_and_injected_input_fail_open(self):
        backend, events = self.make()
        self.assertFalse(backend.process_event(VK_LWIN, "down", foreground_hwnd=999))
        self.assertFalse(backend.process_event(VK_LWIN, "down", physical=False))
        backend.deactivate()
        self.assertFalse(backend.process_event(VK_LWIN, "down"))
        self.assertFalse(events)

    def test_deactivate_clears_win_session_and_next_activation_is_clean(self):
        backend, events = self.make()
        self.assertTrue(backend.process_event(VK_LWIN, "down"))
        backend.deactivate()
        self.assertFalse(backend.process_event(ord("R"), "down"))
        self.assertFalse(backend.process_event(VK_LWIN, "up"))
        backend.activate(100)
        self.assertTrue(backend.process_event(VK_LWIN, "down"))
        self.assertTrue(backend.process_event(VK_LWIN, "up"))
        self.assertEqual(events, [("Win", "down"), ("Win", "down"), ("Win", "up")])


if __name__ == "__main__":
    unittest.main()
