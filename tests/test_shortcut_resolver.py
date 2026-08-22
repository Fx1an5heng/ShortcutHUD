import unittest

from scripts.shortcut_resolver import ShortcutEntry, resolve_shortcuts


class ShortcutResolverTests(unittest.TestCase):
    def test_known_application_returns_app_plus_global(self) -> None:
        data = {
            "CODE.EXE": {"Ctrl": {"S": "Save", "P": "Quick Open"}},
            "DEFAULT": {"Ctrl": {"C": "Copy"}},
            "GLOBAL": {"Ctrl": {"G": "Global Action"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "code.exe", "Ctrl"),
            [
                ShortcutEntry("S", "Save", "APP"),
                ShortcutEntry("P", "Quick Open", "APP"),
                ShortcutEntry("G", "Global Action", "GLOBAL"),
            ],
        )

    def test_unknown_application_returns_default_plus_global(self) -> None:
        data = {
            "CODE.EXE": {"Ctrl": {"S": "Save"}},
            "DEFAULT": {"Ctrl": {"C": "Copy"}},
            "GLOBAL": {"Ctrl": {"G": "Global Action"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "unknown.exe", "Ctrl"),
            [
                ShortcutEntry("C", "Copy", "DEFAULT"),
                ShortcutEntry("G", "Global Action", "GLOBAL"),
            ],
        )

    def test_app_wins_same_key_conflict_with_global(self) -> None:
        data = {
            "CODE.EXE": {"Ctrl": {"S": "App Save"}},
            "GLOBAL": {"Ctrl": {"S": "Global Save", "G": "Global Action"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Ctrl"),
            [
                ShortcutEntry("S", "App Save", "APP"),
                ShortcutEntry("G", "Global Action", "GLOBAL"),
            ],
        )

    def test_app_uppercase_key_wins_lowercase_global_conflict(self) -> None:
        data = {
            "CODE.EXE": {"Ctrl": {"S": "App Save"}},
            "GLOBAL": {"Ctrl": {"s": "Global Save"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Ctrl"),
            [ShortcutEntry("S", "App Save", "APP")],
        )

    def test_app_lowercase_key_wins_uppercase_global_conflict(self) -> None:
        data = {
            "CODE.EXE": {"Ctrl": {"s": "App Save"}},
            "GLOBAL": {"Ctrl": {"S": "Global Save"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Ctrl"),
            [ShortcutEntry("s", "App Save", "APP")],
        )

    def test_default_wins_same_key_conflict_with_global(self) -> None:
        data = {
            "DEFAULT": {"Ctrl": {"C": "Default Copy"}},
            "GLOBAL": {"Ctrl": {"C": "Global Copy", "G": "Global Action"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "unknown.exe", "Ctrl"),
            [
                ShortcutEntry("C", "Default Copy", "DEFAULT"),
                ShortcutEntry("G", "Global Action", "GLOBAL"),
            ],
        )

    def test_missing_global_layer_is_empty_not_an_error(self) -> None:
        data = {"CODE.EXE": {"Ctrl": {"S": "Save"}}}

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Ctrl"),
            [ShortcutEntry("S", "Save", "APP")],
        )

    def test_multilingual_description_is_passed_through_unchanged(self) -> None:
        description = {"en": "Save", "zh": "保存"}
        data = {"CODE.EXE": {"Ctrl": {"S": description}}}

        entries = resolve_shortcuts(data, "CODE.EXE", "Ctrl")

        self.assertEqual(entries, [ShortcutEntry("S", description, "APP")])
        self.assertIs(entries[0].description, description)

    def test_none_foreground_returns_default_plus_global(self) -> None:
        data = {
            "DEFAULT": {"Ctrl": {"C": "Copy"}},
            "GLOBAL": {"Ctrl": {"G": "Global Action"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, None, "Ctrl"),
            [
                ShortcutEntry("C", "Copy", "DEFAULT"),
                ShortcutEntry("G", "Global Action", "GLOBAL"),
            ],
        )

    def test_full_windows_path_identifies_application_executable(self) -> None:
        data = {"CODE.EXE": {"Ctrl": {"S": "Save"}}}

        self.assertEqual(
            resolve_shortcuts(
                data,
                r"C:\Program Files\Microsoft VS Code\Code.exe",
                "Ctrl",
            ),
            [ShortcutEntry("S", "Save", "APP")],
        )

    def test_unknown_modifier_returns_empty_list(self) -> None:
        data = {"CODE.EXE": {"Ctrl": {"S": "Save"}}}

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Ctrl+Hyper"),
            [],
        )

    def test_insertion_order_is_preserved_across_layers(self) -> None:
        data = {
            "CODE.EXE": {
                "Ctrl": {
                    "Z": "First app item",
                    "A": "Second app item",
                }
            },
            "GLOBAL": {
                "Ctrl": {
                    "Y": "First global item",
                    "B": "Second global item",
                }
            },
        }

        entries = resolve_shortcuts(data, "CODE.EXE", "Ctrl")

        self.assertEqual([entry.key for entry in entries], ["Z", "A", "Y", "B"])

    def test_equivalent_modifier_groups_both_participate_in_order(self) -> None:
        data = {
            "CODE.EXE": {
                "Ctrl": {
                    "A": "First group first",
                    "S": "First group wins conflict",
                },
                "ctrl": {
                    "s": "Second group loses conflict",
                    "B": "Second group unique",
                },
            }
        }

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Ctrl"),
            [
                ShortcutEntry("A", "First group first", "APP"),
                ShortcutEntry("S", "First group wins conflict", "APP"),
                ShortcutEntry("B", "Second group unique", "APP"),
            ],
        )

    def test_arbitrary_key_strings_are_not_filtered_by_ui_shape(self) -> None:
        opaque_keys = ["PAGEUP", "LEFT", "PRTSC"]
        data = {
            "CODE.EXE": {
                "Ctrl": {key: f"Description for {key}" for key in opaque_keys},
                "Ctrl+K Ctrl+S": {"": "Keyboard shortcuts"},
            }
        }

        entries = resolve_shortcuts(data, "CODE.EXE", "Ctrl")

        self.assertEqual(
            [entry.key for entry in entries],
            [*opaque_keys, "Ctrl+K Ctrl+S"],
        )

    def test_configured_modifier_aliases_match_canonical_input(self) -> None:
        data = {
            "CODE.EXE": {
                "Shift+Alt": {"F": "Format"},
                "Win+Shift": {"S": "Screenshot"},
                "Win+Ctrl": {"D": "Desktop"},
            }
        }

        cases = {
            "Alt+Shift": "F",
            "Shift+Win": "S",
            "Ctrl+Win": "D",
        }
        for canonical_modifier, expected_key in cases.items():
            with self.subTest(canonical_modifier=canonical_modifier):
                entries = resolve_shortcuts(
                    data,
                    "CODE.EXE",
                    canonical_modifier,
                )
                self.assertEqual([entry.key for entry in entries], [expected_key])

    def test_known_app_does_not_fall_back_to_default_for_missing_modifier(self) -> None:
        data = {
            "CODE.EXE": {"Ctrl": {"S": "Save"}},
            "DEFAULT": {"Alt": {"F4": "Close"}},
            "GLOBAL": {"Alt": {"G": "Global Alt"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Alt"),
            [ShortcutEntry("G", "Global Alt", "GLOBAL")],
        )

    def test_no_modifier_is_outside_modifier_triggered_resolver(self) -> None:
        data = {
            "CODE.EXE": {"NoModifier": {"A": "Unmodified action"}},
            "DEFAULT": {"NoModifier": {"B": "Default action"}},
            "GLOBAL": {"NoModifier": {"C": "Global action"}},
        }

        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "NoModifier"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
