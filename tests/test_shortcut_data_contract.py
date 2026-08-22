import json
from pathlib import Path
import unittest

from scripts.shortcut_resolver import resolve_shortcuts


_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
)
_EXPECTED_GLOBAL_WIN_KEYS = ["R", "E", "V", "D", "I", "S", "Tab", "X"]


class ShortcutDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with _CONFIG_PATH.open(encoding="utf-8") as config_file:
            cls.shortcut_data = json.load(config_file)

    def test_known_explorer_win_resolves_global_entries(self) -> None:
        entries = resolve_shortcuts(
            self.shortcut_data,
            "EXPLORER.EXE",
            "Win",
        )

        self.assertEqual(
            [entry.key for entry in entries],
            _EXPECTED_GLOBAL_WIN_KEYS,
        )
        self.assertTrue(all(entry.source == "GLOBAL" for entry in entries))

    def test_unknown_application_win_resolves_global_entries(self) -> None:
        entries = resolve_shortcuts(
            self.shortcut_data,
            "UNCONFIGURED.EXE",
            "Win",
        )

        self.assertEqual(
            [entry.key for entry in entries],
            _EXPECTED_GLOBAL_WIN_KEYS,
        )
        self.assertTrue(all(entry.source == "GLOBAL" for entry in entries))

    def test_vscode_quick_open_and_command_palette_are_distinct(self) -> None:
        code_shortcuts = self.shortcut_data["CODE.EXE"]

        self.assertEqual(
            code_shortcuts["Ctrl"]["P"]["en"],
            "Quick Open",
        )
        self.assertEqual(
            code_shortcuts["Ctrl+Shift"]["P"]["en"],
            "Command Palette",
        )

    def test_vscode_incorrect_ctrl_shift_bindings_are_absent(self) -> None:
        shortcuts = self.shortcut_data["CODE.EXE"]["Ctrl+Shift"]

        if "S" in shortcuts:
            self.assertEqual(shortcuts["S"]["en"], "Save As")
            self.assertNotEqual(shortcuts["S"]["en"], "Save All")
        if "O" in shortcuts:
            self.assertEqual(shortcuts["O"]["en"], "Go to Symbol")
        if "A" in shortcuts:
            self.assertNotEqual(shortcuts["A"]["en"], "Block Comment")

    def test_vscode_ctrl_first_screen_is_curated(self) -> None:
        configured = self.shortcut_data["CODE.EXE"]["Ctrl"]
        first_screen = resolve_shortcuts(
            self.shortcut_data,
            "CODE.EXE",
            "Ctrl",
        )[:8]

        self.assertLessEqual(len(configured), 8)
        self.assertEqual(
            [entry.key for entry in first_screen[:4]],
            ["P", "`", "/", "B"],
        )
        self.assertTrue(all(entry.source == "APP" for entry in first_screen))
        self.assertTrue(
            {"C", "V", "X", "Z"}.isdisjoint(
                entry.key.upper() for entry in first_screen
            )
        )

    def test_vscode_ctrl_shift_first_screen_is_curated(self) -> None:
        configured = self.shortcut_data["CODE.EXE"]["Ctrl+Shift"]
        entries = resolve_shortcuts(
            self.shortcut_data,
            "CODE.EXE",
            "Ctrl+Shift",
        )

        self.assertLessEqual(len(configured), 8)
        self.assertEqual(
            [entry.key for entry in entries[:4]],
            ["P", "F", "E", "G"],
        )

    def test_vscode_keyboard_shortcuts_chord_is_deferred(self) -> None:
        entries = resolve_shortcuts(
            self.shortcut_data,
            "CODE.EXE",
            "Ctrl",
        )

        self.assertNotIn("Ctrl+K Ctrl+S", self.shortcut_data["CODE.EXE"])
        self.assertNotIn("Ctrl+K Ctrl+S", [entry.key for entry in entries])

    def test_edge_ctrl_is_application_specific_and_curated(self) -> None:
        self.assertIn("MSEDGE.EXE", self.shortcut_data)
        entries = resolve_shortcuts(
            self.shortcut_data,
            "msedge.exe",
            "Ctrl",
        )
        keys = [entry.key for entry in entries]

        self.assertTrue(
            {"T", "W", "L", "R", "H", "J", "D", "Tab"}.issubset(keys)
        )
        self.assertTrue(all(entry.source == "APP" for entry in entries))
        self.assertTrue({"C", "V", "X", "Z", "A"}.isdisjoint(keys))

    def test_edge_ctrl_shift_contains_high_value_browser_actions(self) -> None:
        entries = resolve_shortcuts(
            self.shortcut_data,
            "MSEDGE.EXE",
            "Ctrl+Shift",
        )
        keys = {entry.key for entry in entries}

        self.assertTrue({"T", "N", "O", "I"}.issubset(keys))
        self.assertTrue(all(entry.source == "APP" for entry in entries))

    def test_config_contains_no_windows_screenshot_shortcuts(self) -> None:
        forbidden_keys = {"prtsc", "printscreen", "print screen"}
        forbidden_descriptions = (
            "screenshot",
            "screen snip",
            "scrnsht",
            "截图",
        )

        for application, modifier_groups in self.shortcut_data.items():
            for modifier, shortcuts in modifier_groups.items():
                modifier_tokens = {
                    token.casefold() for token in modifier.split("+")
                }
                for key, description in shortcuts.items():
                    location = f"{application}.{modifier}.{key}"
                    key_identity = key.casefold()
                    description_text = json.dumps(
                        description,
                        ensure_ascii=False,
                    ).casefold()

                    self.assertNotIn(
                        key_identity,
                        forbidden_keys,
                        location,
                    )
                    if modifier_tokens == {"win", "shift"}:
                        self.assertNotEqual(key_identity, "s", location)
                    for forbidden in forbidden_descriptions:
                        self.assertNotIn(
                            forbidden,
                            description_text,
                            location,
                        )


if __name__ == "__main__":
    unittest.main()
