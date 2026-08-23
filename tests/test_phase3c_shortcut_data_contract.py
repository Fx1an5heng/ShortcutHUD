import json
from pathlib import Path
import unittest

from scripts.shortcut_resolver import resolve_shortcuts


_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"


class Phase3CShortcutDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with _CONFIG_PATH.open(encoding="utf-8") as config_file:
            cls.shortcut_data = json.load(config_file)

    def _resolved_keys(self, application: str, modifier: str) -> list[str]:
        return [
            entry.key
            for entry in resolve_shortcuts(
                self.shortcut_data,
                application,
                modifier,
            )
            if entry.source == "APP"
        ]

    def _assert_app_entries(self, application: str, modifier: str) -> None:
        entries = resolve_shortcuts(
            self.shortcut_data,
            application,
            modifier,
        )
        app_entries = [entry for entry in entries if entry.source == "APP"]
        self.assertTrue(app_entries, f"{application}.{modifier}")

    def test_vscode_ctrl_matches_user_selected_first_screen(self) -> None:
        self.assertEqual(
            self._resolved_keys("CODE.EXE", "Ctrl"),
            ["P", "`", "/", "B", "G", "H", "Enter", "L"],
        )
        self._assert_app_entries("CODE.EXE", "Ctrl")

    def test_edge_and_chrome_ctrl_are_nine_entry_app_packs(self) -> None:
        expected_keys = ["T", "W", "L", "Tab", "R", "H", "J", "D", "N"]

        for application in ("MSEDGE.EXE", "CHROME.EXE"):
            with self.subTest(application=application):
                self.assertEqual(
                    self._resolved_keys(application, "Ctrl"),
                    expected_keys,
                )
                self._assert_app_entries(application, "Ctrl")

    def test_browser_ctrl_shift_packs_match_selected_actions(self) -> None:
        self.assertEqual(
            self._resolved_keys("MSEDGE.EXE", "Ctrl+Shift"),
            ["T", "N", "O", "I", "R", "K", "Tab", "Delete"],
        )
        self.assertEqual(
            self._resolved_keys("CHROME.EXE", "Ctrl+Shift"),
            ["T", "N", "O", "J", "R", "Tab", "Delete", "B"],
        )

    def test_explorer_pack_removes_legacy_history_and_dead_data(self) -> None:
        explorer = self.shortcut_data["EXPLORER.EXE"]

        self.assertEqual(list(explorer["Ctrl"]), ["L", "T", "W", "Tab", "N", "E", "D"])
        self.assertNotIn("H", explorer["Ctrl"])
        self.assertNotIn("NoModifier", explorer)
        self.assertEqual(
            self._resolved_keys("EXPLORER.EXE", "Ctrl+Shift"),
            ["N", "Tab", "E", "2", "6"],
        )

    def test_windows_terminal_runtime_executable_resolves_app_entries(self) -> None:
        self.assertIn("WINDOWSTERMINAL.EXE", self.shortcut_data)

        expected_groups = {
            "Ctrl": ["Tab", ",", "+", "-", "0"],
            "Ctrl+Shift": ["T", "W", "P", "F", "D", "N", "C", "V"],
            "Alt": ["UP", "DOWN", "LEFT", "RIGHT"],
            "Alt+Shift": ["D", "-", "+", "UP", "DOWN", "LEFT", "RIGHT"],
        }
        for modifier, expected_keys in expected_groups.items():
            with self.subTest(modifier=modifier):
                self.assertEqual(
                    self._resolved_keys("WindowsTerminal.exe", modifier),
                    expected_keys,
                )
                self._assert_app_entries("WindowsTerminal.exe", modifier)

    def test_microsoft_office_selected_shortcuts_are_present(self) -> None:
        expected_keys = {
            ("WINWORD.EXE", "Ctrl"): {"B", "I", "U", "H", "K", "Enter", "E", "J"},
            ("WINWORD.EXE", "Ctrl+Alt"): {"1", "2", "3", "M", "F", "D", "P", "O"},
            ("EXCEL.EXE", "Ctrl"): {"1", "T", "D", "E", ";", "`", "PageUp", "PageDown"},
            ("EXCEL.EXE", "Ctrl+Alt"): {"V", "F5"},
            ("POWERPNT.EXE", "Ctrl"): {"M", "G", "K", "+", "-", "UP", "DOWN", "F1"},
            ("POWERPNT.EXE", "Ctrl+Alt"): {"M", "V", "O"},
        }

        for (application, modifier), required_keys in expected_keys.items():
            with self.subTest(application=application, modifier=modifier):
                entries = resolve_shortcuts(
                    self.shortcut_data,
                    application,
                    modifier,
                )
                self.assertTrue(all(entry.source == "APP" for entry in entries))
                self.assertEqual({entry.key for entry in entries}, required_keys)

    def test_audited_app_packs_have_no_no_modifier_group(self) -> None:
        audited_applications = (
            "CODE.EXE",
            "MSEDGE.EXE",
            "EXPLORER.EXE",
            "WINDOWSTERMINAL.EXE",
            "CHROME.EXE",
            "WINWORD.EXE",
            "EXCEL.EXE",
            "POWERPNT.EXE",
        )

        for application in audited_applications:
            with self.subTest(application=application):
                self.assertNotIn(
                    "NoModifier",
                    self.shortcut_data[application],
                )

    def test_wps_presentation_contains_no_screengrab_shortcuts(self) -> None:
        wps_presentation = self.shortcut_data["WPP.EXE"]
        forbidden_terms = ("screengrab", "screenshot", "截图")

        for modifier, shortcuts in wps_presentation.items():
            for key, description in shortcuts.items():
                location = f"WPP.EXE.{modifier}.{key}"
                description_text = json.dumps(
                    description,
                    ensure_ascii=False,
                ).casefold()
                for forbidden in forbidden_terms:
                    self.assertNotIn(forbidden, description_text, location)


if __name__ == "__main__":
    unittest.main()
