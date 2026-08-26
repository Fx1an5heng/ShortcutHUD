import unittest

from scripts.user_shortcut_manager_dialog import (
    ProfileValidationError,
    UserProfileDraft,
    supported_modifier_combinations,
)


class UserProfileDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.initial = {
            "CODE.EXE": {
                "display_name": "My Code",
                "shortcuts": {
                    "Ctrl": {
                        "P": {"en": "Quick Open", "zh": "快速打开"},
                        "F13": {"en": "Test", "zh": "测试"},
                        "K": {"en": "Action", "zh": "功能"},
                    },
                    "Alt": {
                        "Z": {"en": "Wrap", "zh": "自动换行"},
                    },
                },
            }
        }
        self.draft = UserProfileDraft(self.initial)

    def test_existing_profiles_are_loaded_as_a_detached_copy(self) -> None:
        self.assertEqual(self.draft.list_profiles(), ["CODE.EXE"])
        self.draft.set_display_name("CODE.EXE", "Changed")
        self.assertEqual(self.initial["CODE.EXE"]["display_name"], "My Code")

    def test_add_same_app_is_case_insensitive_and_does_not_duplicate(self) -> None:
        self.assertFalse(self.draft.add_profile("code.exe"))
        self.assertEqual(self.draft.list_profiles(), ["CODE.EXE"])

    def test_add_and_delete_profile(self) -> None:
        self.assertTrue(self.draft.add_profile("notepad.exe"))
        self.assertIn("NOTEPAD.EXE", self.draft.list_profiles())
        self.assertTrue(self.draft.delete_profile("NOTEPAD.exe"))

    def test_wps_logical_identity_is_allowed_but_reserved_identity_is_not(self) -> None:
        self.assertTrue(self.draft.add_profile("WPS_PDF"))
        for identity in ("DEFAULT", "GLOBAL", "WINDOWS_SHELL", "WPS_UNKNOWN"):
            with self.subTest(identity=identity):
                with self.assertRaises(ProfileValidationError):
                    self.draft.add_profile(identity)

    def test_empty_display_name_removes_override(self) -> None:
        self.draft.set_display_name("CODE.EXE", "   ")

        self.assertNotIn("display_name", self.draft.get_profile("CODE.EXE"))

    def test_fullwidth_and_halfwidth_symbols_are_the_same_shortcut(self) -> None:
        self.draft.add_shortcut("CODE.EXE", "Ctrl", "?", "问号", "Question")

        with self.assertRaises(ProfileValidationError):
            self.draft.add_shortcut("CODE.EXE", "Ctrl", "？", "全角问号", "Fullwidth")

        shortcuts = self.draft.list_shortcuts("CODE.EXE")
        question_entries = [
            (modifier, key)
            for modifier, key, _description in shortcuts
            if modifier == "Ctrl" and key.casefold() == "?"
        ]
        self.assertEqual(question_entries, [("Ctrl", "?")])

    def test_add_edit_and_delete_shortcut(self) -> None:
        self.draft.add_shortcut("CODE.EXE", "Shift+Ctrl", "J", "新建", "New")
        self.draft.edit_shortcut(
            "CODE.EXE",
            "Ctrl+Shift",
            "J",
            "Alt",
            "F4",
            "关闭",
            "Close",
        )
        entries = self.draft.list_shortcuts("CODE.EXE")
        self.assertIn(("Alt", "F4", {"en": "Close", "zh": "关闭"}), entries)
        self.assertTrue(self.draft.delete_shortcut("CODE.EXE", "alt", "f4"))

    def test_duplicate_key_is_case_insensitive_within_canonical_group(self) -> None:
        with self.assertRaises(ProfileValidationError):
            self.draft.add_shortcut(
                "CODE.EXE", "ctrl", "p", "重复", "Duplicate"
            )

    def test_full_width_symbol_alias_shares_duplicate_identity_with_ascii(self) -> None:
        self.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "？", "问号", "Question mark"
        )
        self.assertIn(
            ("Ctrl", "?", {"en": "Question mark", "zh": "问号"}),
            self.draft.list_shortcuts("CODE.EXE"),
        )
        with self.assertRaises(ProfileValidationError):
            self.draft.add_shortcut(
                "CODE.EXE", "Ctrl", "?", "重复", "Duplicate"
            )

    def test_edit_to_existing_key_is_rejected_without_mutating_draft(self) -> None:
        before = self.draft.snapshot()
        with self.assertRaises(ProfileValidationError):
            self.draft.edit_shortcut(
                "CODE.EXE",
                "Ctrl",
                "F13",
                "Ctrl",
                "p",
                "重复",
                "Duplicate",
            )
        self.assertEqual(self.draft.snapshot(), before)

    def test_empty_key_and_descriptions_are_rejected(self) -> None:
        invalid_values = (
            ("", "中文", "English"),
            ("K", "", "English"),
            ("K", "中文", ""),
        )
        for key, zh, en in invalid_values:
            with self.subTest(key=key, zh=zh, en=en):
                with self.assertRaises(ProfileValidationError):
                    self.draft.add_shortcut("CODE.EXE", "Ctrl", key, zh, en)

    def test_no_modifier_is_not_offered_or_accepted(self) -> None:
        self.assertNotIn("NoModifier", supported_modifier_combinations())
        with self.assertRaises(ProfileValidationError):
            self.draft.add_shortcut(
                "CODE.EXE", "NoModifier", "A", "操作", "Action"
            )

    def test_single_step_modifier_and_key_boundary(self) -> None:
        invalid_terminal_keys = (
            ("Ctrl", "Shift"),
            ("Ctrl+Shift", "Shift"),
            ("Alt", "Ctrl"),
            ("Ctrl", "F99"),
            ("Ctrl", "Ctrl+W, W"),
        )
        for modifier, key in invalid_terminal_keys:
            with self.subTest(modifier=modifier, key=key):
                with self.assertRaises(ProfileValidationError):
                    self.draft.add_shortcut(
                        "CODE.EXE", modifier, key, "说明", "Description"
                    )

        self.draft.add_shortcut(
            "CODE.EXE", "Ctrl+Shift", "p", "命令", "Command"
        )
        self.draft.add_shortcut(
            "CODE.EXE", "Ctrl+Alt", "f5", "运行", "Run"
        )
        entries = self.draft.list_shortcuts("CODE.EXE")
        self.assertIn(
            ("Ctrl+Shift", "P", {"en": "Command", "zh": "命令"}),
            entries,
        )
        self.assertIn(
            ("Ctrl+Alt", "F5", {"en": "Run", "zh": "运行"}),
            entries,
        )

    def test_move_changes_only_the_selected_modifier_group_order(self) -> None:
        self.assertTrue(self.draft.move_shortcut("CODE.EXE", "Ctrl", "F13", -1))
        profile = self.draft.get_profile("CODE.EXE")

        self.assertEqual(
            list(profile["shortcuts"]["Ctrl"]),
            ["F13", "P", "K"],
        )
        self.assertEqual(list(profile["shortcuts"]["Alt"]), ["Z"])

    def test_mark_saved_resets_dirty_state(self) -> None:
        self.assertFalse(self.draft.dirty)
        self.draft.set_display_name("CODE.EXE", "Changed")
        self.assertTrue(self.draft.dirty)
        self.draft.mark_saved()
        self.assertFalse(self.draft.dirty)

    def test_hidden_builtin_operations_are_detached_dirty_and_restore_is_scoped(self) -> None:
        self.assertTrue(
            self.draft.hide_builtin_shortcut("CODE.EXE", "ctrl", "f4")
        )
        self.assertTrue(
            self.draft.hide_builtin_shortcut("CODE.EXE", "Ctrl", "h")
        )
        self.assertFalse(
            self.draft.hide_builtin_shortcut("CODE.EXE", "Ctrl", "F4")
        )

        self.assertTrue(self.draft.dirty)
        self.assertNotIn("hidden_builtin", self.initial["CODE.EXE"])
        self.assertEqual(
            self.draft.list_hidden_builtin_shortcuts("CODE.EXE"),
            [("Ctrl", "F4"), ("Ctrl", "H")],
        )
        self.assertTrue(
            self.draft.restore_builtin_shortcut("CODE.EXE", "Ctrl", "F4")
        )
        self.assertEqual(
            self.draft.list_hidden_builtin_shortcuts("CODE.EXE"),
            [("Ctrl", "H")],
        )

    def test_restore_all_keeps_profile_user_shortcuts_and_display_name(self) -> None:
        self.draft.hide_builtin_shortcut("CODE.EXE", "Ctrl", "H")

        self.assertTrue(self.draft.restore_all_hidden_builtins("CODE.EXE"))

        profile = self.draft.get_profile("CODE.EXE")
        self.assertIn("CODE.EXE", self.draft.list_profiles())
        self.assertEqual(profile["display_name"], "My Code")
        self.assertIn("P", profile["shortcuts"]["Ctrl"])
        self.assertNotIn("hidden_builtin", profile)

    def test_restore_all_does_not_prune_an_existing_empty_profile(self) -> None:
        self.draft.add_profile("EMPTY.EXE")
        self.draft.hide_builtin_shortcut("EMPTY.EXE", "Ctrl", "H")

        self.assertTrue(self.draft.restore_all_hidden_builtins("EMPTY.EXE"))

        self.assertEqual(
            self.draft.get_profile("EMPTY.EXE"),
            {"shortcuts": {}},
        )

    def test_reserved_hidden_builtin_api_is_rejected(self) -> None:
        for identity in ("DEFAULT", "GLOBAL", "WINDOWS_SHELL", "WPS_UNKNOWN"):
            with self.subTest(identity=identity):
                with self.assertRaises(ProfileValidationError):
                    self.draft.hide_builtin_shortcut(identity, "Ctrl", "H")

    def test_validate_all_rejects_noncanonical_hidden_state(self) -> None:
        invalid = UserProfileDraft(
            {
                "CODE.EXE": {
                    "shortcuts": {},
                    "hidden_builtin": {"ctrl": ["h"]},
                }
            }
        )

        with self.assertRaises(ProfileValidationError):
            invalid.validate_all()


if __name__ == "__main__":
    unittest.main()
