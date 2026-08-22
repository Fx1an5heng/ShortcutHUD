import unittest

from PySide6.QtWidgets import QApplication

from scripts.hud_entry_limits import (
    DEFAULT_HUD_ENTRY_LIMIT,
    get_hud_entry_limit,
)
from scripts.shortcut_hud import ShortcutHudWindow
from scripts.shortcut_resolver import ShortcutEntry


class HudEntryLimitTests(unittest.TestCase):
    def test_browser_ctrl_overrides_normalize_app_and_modifier(self) -> None:
        self.assertEqual(
            get_hud_entry_limit(
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                "ctrl",
            ),
            9,
        )
        self.assertEqual(get_hud_entry_limit("chrome.exe", "Ctrl"), 9)

    def test_non_override_pairs_use_default_limit(self) -> None:
        self.assertEqual(
            get_hud_entry_limit("MSEDGE.EXE", "Ctrl+Shift"),
            DEFAULT_HUD_ENTRY_LIMIT,
        )
        self.assertEqual(
            get_hud_entry_limit("WINWORD.EXE", "Ctrl"),
            DEFAULT_HUD_ENTRY_LIMIT,
        )
        self.assertEqual(
            get_hud_entry_limit("MSEDGE.EXE", "Ctrl+"),
            DEFAULT_HUD_ENTRY_LIMIT,
        )


class HudEntryLimitPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def test_browser_ctrl_renders_nine_and_ordinary_app_renders_eight(self) -> None:
        entries = [
            ShortcutEntry(str(index), f"Action {index}", "APP")
            for index in range(10)
        ]

        for application_name, modifier, expected_rows in (
            ("MSEDGE.EXE", "Ctrl", 9),
            ("CHROME.EXE", "Ctrl", 9),
            ("PHOTOSHOP.EXE", "Ctrl", 8),
        ):
            with self.subTest(application_name=application_name):
                hud = ShortcutHudWindow()
                hud.set_entries(
                    application_name,
                    modifier,
                    entries,
                    "en_US",
                )
                self.assertEqual(hud._entries_layout.count(), expected_rows)
                hud.deleteLater()


if __name__ == "__main__":
    unittest.main()
