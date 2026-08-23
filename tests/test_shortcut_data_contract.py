import json
from pathlib import Path
import unittest

from scripts.shortcut_resolver import resolve_shortcuts


_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
)
_EXPECTED_GLOBAL_WIN_KEYS = ["R", "E", "V", "D", "I", "S", "Tab", "X"]
_EXPECTED_GLOBAL_WIN = {
    "R": {"en": "Run", "zh": "运行"},
    "E": {"en": "File Explorer", "zh": "文件资源管理器"},
    "V": {"en": "Clipboard history", "zh": "剪贴板历史"},
    "D": {"en": "Show/hide desktop", "zh": "显示/隐藏桌面"},
    "I": {"en": "Settings", "zh": "设置"},
    "S": {"en": "Search", "zh": "搜索"},
    "Tab": {"en": "Task View", "zh": "任务视图"},
    "X": {"en": "Quick Link menu", "zh": "快速链接菜单"},
}


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
        self.assertTrue(
            all(
                entry.source == "APP"
                for entry in entries
                if entry.key != "Esc"
            )
        )
        self.assertEqual(
            [(entry.key, entry.source) for entry in entries if entry.source == "GLOBAL"],
            [("Esc", "GLOBAL")],
        )

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


    def test_phase4d_global_data_contract(self) -> None:
        global_shortcuts = self.shortcut_data["GLOBAL"]

        self.assertEqual(set(global_shortcuts), {"Win", "Alt", "Ctrl+Shift"})
        self.assertEqual(global_shortcuts["Win"], _EXPECTED_GLOBAL_WIN)
        self.assertEqual(
            global_shortcuts["Alt"],
            {
                "Tab": {"en": "Switch windows", "zh": "切换窗口"},
                "F4": {
                    "en": "Close current window",
                    "zh": "关闭当前窗口",
                },
            },
        )
        self.assertEqual(
            global_shortcuts["Ctrl+Shift"],
            {"Esc": {"en": "Task Manager", "zh": "任务管理器"}},
        )
        self.assertEqual(self.shortcut_data["WINDOWS_SHELL"], {})

        default_alt_keys = {
            key.casefold() for key in self.shortcut_data["DEFAULT"]["Alt"]
        }
        default_ctrl_shift_keys = {
            key.casefold()
            for key in self.shortcut_data["DEFAULT"]["Ctrl+Shift"]
        }
        self.assertTrue({"tab", "f4"}.isdisjoint(default_alt_keys))
        self.assertNotIn("esc", default_ctrl_shift_keys)

    def test_windows_shell_resolves_global_only_and_never_default(self) -> None:
        win_entries = resolve_shortcuts(
            self.shortcut_data,
            "WINDOWS_SHELL",
            "Win",
        )
        alt_entries = resolve_shortcuts(
            self.shortcut_data,
            "WINDOWS_SHELL",
            "Alt",
        )
        task_manager_entries = resolve_shortcuts(
            self.shortcut_data,
            "WINDOWS_SHELL",
            "Ctrl+Shift",
        )
        ctrl_entries = resolve_shortcuts(
            self.shortcut_data,
            "WINDOWS_SHELL",
            "Ctrl",
        )

        self.assertEqual(
            [entry.key for entry in win_entries],
            _EXPECTED_GLOBAL_WIN_KEYS,
        )
        self.assertTrue(all(entry.source == "GLOBAL" for entry in win_entries))
        self.assertEqual(
            [(entry.key, entry.source) for entry in alt_entries],
            [("Tab", "GLOBAL"), ("F4", "GLOBAL")],
        )
        self.assertEqual(
            [(entry.key, entry.source) for entry in task_manager_entries],
            [("Esc", "GLOBAL")],
        )
        self.assertEqual(ctrl_entries, [])


    def test_wps_unknown_resolves_each_configured_global_group_only(self) -> None:
        expected_keys = {
            "Win": _EXPECTED_GLOBAL_WIN_KEYS,
            "Alt": ["Tab", "F4"],
            "Ctrl+Shift": ["Esc"],
        }

        for modifier, keys in expected_keys.items():
            with self.subTest(modifier=modifier):
                entries = resolve_shortcuts(
                    self.shortcut_data,
                    "WPS_UNKNOWN",
                    modifier,
                )
                self.assertEqual([entry.key for entry in entries], keys)
                self.assertTrue(
                    all(entry.source == "GLOBAL" for entry in entries)
                )


    def test_unknown_third_party_receives_every_global_group(self) -> None:
        expected_global_keys = {
            "Alt": ["Tab", "F4"],
            "Ctrl+Shift": ["Esc"],
            "Win": _EXPECTED_GLOBAL_WIN_KEYS,
        }

        for modifier, expected_keys in expected_global_keys.items():
            with self.subTest(modifier=modifier):
                entries = resolve_shortcuts(
                    self.shortcut_data,
                    "UNKNOWN_THIRD_PARTY.EXE",
                    modifier,
                )
                global_entries = [
                    entry for entry in entries if entry.source == "GLOBAL"
                ]
                self.assertEqual(
                    [entry.key for entry in global_entries],
                    expected_keys,
                )

    def test_known_app_without_alt_receives_global_alt_only(self) -> None:
        self.assertNotIn("Alt", self.shortcut_data["WINWORD.EXE"])

        entries = resolve_shortcuts(
            self.shortcut_data,
            "WINWORD.EXE",
            "Alt",
        )

        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [("Tab", "GLOBAL"), ("F4", "GLOBAL")],
        )

    def test_known_app_with_alt_keeps_local_then_global(self) -> None:
        entries = resolve_shortcuts(
            self.shortcut_data,
            "CODE.EXE",
            "Alt",
        )
        sources = [entry.source for entry in entries]

        self.assertTrue(sources)
        first_global = sources.index("GLOBAL")
        self.assertTrue(all(source == "APP" for source in sources[:first_global]))
        self.assertEqual(
            [(entry.key, entry.source) for entry in entries[first_global:]],
            [("Tab", "GLOBAL"), ("F4", "GLOBAL")],
        )


if __name__ == "__main__":
    unittest.main()
