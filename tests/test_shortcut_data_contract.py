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
