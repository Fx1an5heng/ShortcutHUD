import unittest

from scripts.shortcut_resolver import ShortcutEntry, resolve_shortcuts


class UserShortcutResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = {
            "CODE.EXE": {
                "Ctrl": {
                    "P": "Built-in Quick Open",
                    "B": "Built-in Sidebar",
                    "K": "Built-in Action K",
                },
                "Alt": {"LEFT": "Navigate Back"},
            },
            "DEFAULT": {
                "Ctrl": {"C": "Default Copy"},
                "Alt": {"ESC": "Default Escape"},
            },
            "GLOBAL": {
                "Ctrl": {"G": "Global Ctrl"},
                "Alt": {
                    "Tab": "Switch windows",
                    "F4": "Close current window",
                },
                "Win": {"R": "Run"},
            },
            "WINDOWS_SHELL": {},
            "WPS_UNKNOWN": {},
            "WPS_WRITER": {"Ctrl": {"B": "Bold"}},
        }

    @staticmethod
    def _profile(shortcuts: dict[str, object], display_name: str | None = None):
        profile: dict[str, object] = {"shortcuts": shortcuts}
        if display_name is not None:
            profile["display_name"] = display_name
        return profile

    def test_user_wins_same_key_over_builtin_app(self) -> None:
        users = {
            "CODE.EXE": self._profile(
                {"Ctrl": {"P": "My Quick Open"}}
            )
        }

        self.assertEqual(
            resolve_shortcuts(self.data, "CODE.EXE", "Ctrl", users),
            [
                ShortcutEntry("P", "My Quick Open", "USER_APP"),
                ShortcutEntry("B", "Built-in Sidebar", "APP"),
                ShortcutEntry("K", "Built-in Action K", "APP"),
                ShortcutEntry("G", "Global Ctrl", "GLOBAL"),
            ],
        )

    def test_user_extra_precedes_surviving_builtin_in_insertion_order(self) -> None:
        users = {
            "CODE.EXE": self._profile(
                {"Ctrl": {"X1": "User first", "X2": "User second"}}
            )
        }

        entries = resolve_shortcuts(self.data, "code.exe", "Ctrl", users)

        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [
                ("X1", "USER_APP"),
                ("X2", "USER_APP"),
                ("P", "APP"),
                ("B", "APP"),
                ("K", "APP"),
                ("G", "GLOBAL"),
            ],
        )

    def test_user_only_application_uses_user_plus_global_without_default(self) -> None:
        users = {
            "BILIBILI.EXE": self._profile(
                {"Alt": {"F": "Fullscreen"}}
            )
        }

        alt_entries = resolve_shortcuts(self.data, "bilibili.exe", "Alt", users)
        ctrl_entries = resolve_shortcuts(self.data, "bilibili.exe", "Ctrl", users)

        self.assertEqual(
            [(entry.key, entry.source) for entry in alt_entries],
            [("F", "USER_APP"), ("Tab", "GLOBAL"), ("F4", "GLOBAL")],
        )
        self.assertEqual(
            [(entry.key, entry.source) for entry in ctrl_entries],
            [("G", "GLOBAL")],
        )

    def test_display_name_only_profile_is_known_and_blocks_default(self) -> None:
        users = {
            "BILIBILI.EXE": self._profile({}, "哔哩哔哩")
        }

        self.assertEqual(
            resolve_shortcuts(self.data, "BILIBILI.EXE", "Ctrl", users),
            [ShortcutEntry("G", "Global Ctrl", "GLOBAL")],
        )

    def test_no_user_unknown_app_keeps_default_plus_global(self) -> None:
        self.assertEqual(
            resolve_shortcuts(self.data, "UNKNOWN.EXE", "Ctrl", {}),
            [
                ShortcutEntry("C", "Default Copy", "DEFAULT"),
                ShortcutEntry("G", "Global Ctrl", "GLOBAL"),
            ],
        )

    def test_no_user_builtin_app_keeps_app_plus_global(self) -> None:
        entries = resolve_shortcuts(self.data, "CODE.EXE", "Ctrl", {})
        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [
                ("P", "APP"),
                ("B", "APP"),
                ("K", "APP"),
                ("G", "GLOBAL"),
            ],
        )

    def test_user_wins_global_conflict_case_insensitively(self) -> None:
        users = {
            "CODE.EXE": self._profile(
                {"Alt": {"f4": "My Close", "X": "User X"}}
            )
        }

        entries = resolve_shortcuts(self.data, "CODE.EXE", "Alt", users)

        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [
                ("f4", "USER_APP"),
                ("X", "USER_APP"),
                ("LEFT", "APP"),
                ("Tab", "GLOBAL"),
            ],
        )

    def test_builtin_app_still_wins_global_conflict(self) -> None:
        data = {
            "CODE.EXE": {"Alt": {"F4": "Local Close"}},
            "GLOBAL": {"Alt": {"f4": "Global Close", "Tab": "Switch"}},
        }
        self.assertEqual(
            resolve_shortcuts(data, "CODE.EXE", "Alt", {}),
            [
                ShortcutEntry("F4", "Local Close", "APP"),
                ShortcutEntry("Tab", "Switch", "GLOBAL"),
            ],
        )

    def test_user_builtin_global_order_and_sources_are_exact(self) -> None:
        users = {
            "CODE.EXE": self._profile(
                {"Alt": {"X": "User X"}}
            )
        }

        entries = resolve_shortcuts(self.data, "CODE.EXE", "Alt", users)

        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [
                ("X", "USER_APP"),
                ("LEFT", "APP"),
                ("Tab", "GLOBAL"),
                ("F4", "GLOBAL"),
            ],
        )

    def test_reserved_identities_ignore_even_malicious_user_profiles(self) -> None:
        users = {
            "WINDOWS_SHELL": self._profile(
                {"Alt": {"X": "Malicious shell local"}}
            ),
            "WPS_UNKNOWN": self._profile(
                {"Alt": {"Y": "Malicious WPS local"}}
            ),
        }

        for app_id in ("WINDOWS_SHELL", "WPS_UNKNOWN"):
            with self.subTest(app_id=app_id):
                self.assertEqual(
                    resolve_shortcuts(self.data, app_id, "Alt", users),
                    [
                        ShortcutEntry("Tab", "Switch windows", "GLOBAL"),
                        ShortcutEntry("F4", "Close current window", "GLOBAL"),
                    ],
                )

    def test_wps_logical_identity_can_receive_user_overlay(self) -> None:
        users = {
            "WPS_WRITER": self._profile(
                {"Ctrl": {"B": "My Bold", "H": "My Replace"}}
            )
        }

        self.assertEqual(
            resolve_shortcuts(self.data, "WPS_WRITER", "Ctrl", users),
            [
                ShortcutEntry("B", "My Bold", "USER_APP"),
                ShortcutEntry("H", "My Replace", "USER_APP"),
                ShortcutEntry("G", "Global Ctrl", "GLOBAL"),
            ],
        )

    def test_update_snapshot_changes_resolution_without_disk_access(self) -> None:
        first = {
            "CODE.EXE": self._profile({"Ctrl": {"P": "First"}})
        }
        second = {
            "CODE.EXE": self._profile({"Ctrl": {"P": "Second"}})
        }

        self.assertEqual(
            resolve_shortcuts(self.data, "CODE.EXE", "Ctrl", first)[0].description,
            "First",
        )
        self.assertEqual(
            resolve_shortcuts(self.data, "CODE.EXE", "Ctrl", second)[0].description,
            "Second",
        )


if __name__ == "__main__":
    unittest.main()
