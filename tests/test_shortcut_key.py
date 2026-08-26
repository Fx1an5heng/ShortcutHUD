import json
from pathlib import Path
import unittest

from scripts.shortcut_key import (
    InvalidShortcutKeyError,
    ModifierTerminalKeyError,
    UnsupportedShortcutSequenceError,
    normalize_shortcut_key,
)


class ShortcutKeyNormalizationTests(unittest.TestCase):
    def test_valid_keys_normalize_to_product_spelling(self) -> None:
        expected = {
            "A": "A",
            "z": "Z",
            "0": "0",
            "9": "9",
            "F1": "F1",
            "f13": "F13",
            "F24": "F24",
            "Enter": "Enter",
            "enter": "Enter",
            "Esc": "Esc",
            "escape": "Esc",
            "Tab": "Tab",
            "PageUp": "PageUp",
            "pageup": "PageUp",
            "pagedown": "PageDown",
            "Left": "Left",
            "left": "Left",
            "lmb": "LMB",
            "MMB": "MMB",
            "rmb": "RMB",
            "`": "`",
            "/": "/",
            "-": "-",
            "\\": "\\",
        }
        for raw_key, canonical_key in expected.items():
            with self.subTest(raw_key=raw_key):
                self.assertEqual(normalize_shortcut_key(raw_key), canonical_key)

    def test_full_width_punctuation_aliases_normalize_to_ascii_symbols(self) -> None:
        expected = {
            "？": "?",
            "！": "!",
            "，": ",",
            "．": ".",
            "。": ".",
            "；": ";",
            "：": ":",
            "（": "(",
            "）": ")",
            "＂": '"',
            "＃": "#",
            "＄": "$",
            "％": "%",
            "＆": "&",
            "＇": "'",
            "＊": "*",
            "＋": "+",
            "－": "-",
            "／": "/",
            "＜": "<",
            "＝": "=",
            "＞": ">",
            "＠": "@",
            "［": "[",
            "＼": "\\",
            "］": "]",
            "＾": "^",
            "＿": "_",
            "｀": "`",
            "｛": "{",
            "｜": "|",
            "｝": "}",
            "～": "~",
        }
        for raw_key, canonical_key in expected.items():
            with self.subTest(raw_key=raw_key):
                self.assertEqual(normalize_shortcut_key(raw_key), canonical_key)

    def test_full_width_non_punctuation_is_not_implicitly_normalized(self) -> None:
        for key in ("Ａ", "１", "￥", "、", "《", "》", "「", "」"):
            with self.subTest(key=key):
                with self.assertRaises(InvalidShortcutKeyError):
                    normalize_shortcut_key(key)

    def test_existing_builtin_single_key_inventory_remains_supported(self) -> None:
        shortcut_path = (
            Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        )
        shortcut_data = json.loads(shortcut_path.read_text(encoding="utf-8"))
        configured_keys = {
            key
            for application in shortcut_data.values()
            for shortcut_group in application.values()
            for key in shortcut_group
            if key
        }

        for key in sorted(configured_keys):
            with self.subTest(key=key):
                normalize_shortcut_key(key)

    def test_truly_invalid_keys_are_rejected(self) -> None:
        for key in (
            "",
            "   ",
            "F0",
            "F25",
            "F99",
            "HELLO",
            "ABC",
            "CtrlP",
            "Ctrl+P",
            "NotAKey",
        ):
            with self.subTest(key=key):
                with self.assertRaises(InvalidShortcutKeyError):
                    normalize_shortcut_key(key)

    def test_modifier_names_are_rejected_as_terminal_keys(self) -> None:
        expected = {
            "Ctrl": "Ctrl",
            "ctrl": "Ctrl",
            "Control": "Ctrl",
            "Alt": "Alt",
            "Shift": "Shift",
            "Win": "Win",
            "Windows": "Win",
        }
        for key, canonical_modifier in expected.items():
            with self.subTest(key=key):
                with self.assertRaises(ModifierTerminalKeyError) as raised:
                    normalize_shortcut_key(key)
                self.assertEqual(raised.exception.modifier, canonical_modifier)

    def test_multi_step_patterns_are_unsupported_not_conceptually_invalid(self) -> None:
        for shortcut in (
            "Ctrl+W, W",
            "Ctrl+K Ctrl+S",
            "Ctrl+K, Ctrl+S",
            "g g",
            "d d",
            "gg",
            "dd",
        ):
            with self.subTest(shortcut=shortcut):
                with self.assertRaises(UnsupportedShortcutSequenceError):
                    normalize_shortcut_key(shortcut)


if __name__ == "__main__":
    unittest.main()
