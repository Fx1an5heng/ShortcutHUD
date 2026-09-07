import unittest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from scripts.application_display_names import get_application_display_name
from scripts.hud_entry_limits import get_hud_entry_limit
from scripts.shortcut_hud import (
    ShortcutHudWindow,
    select_description_text,
    select_visible_entry_groups,
)
from scripts.shortcut_resolver import ShortcutEntry, resolve_shortcuts
from scripts.shell_identity import WINDOWS_DESKTOP, WINDOWS_SHELL
from scripts.wps_identity import (
    WPS_PDF,
    WPS_PRESENTATION,
    WPS_UNKNOWN,
    WPS_WRITER,
)


class ShortcutHudPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def test_wps_logical_ids_have_user_facing_display_names(self) -> None:
        expected_labels = {
            WPS_WRITER: "WPS Writer",
            WPS_PDF: "WPS PDF",
            WPS_PRESENTATION: "WPS Presentation",
        }
        for application_name, expected_label in expected_labels.items():
            with self.subTest(application_name=application_name):
                self.assertEqual(
                    get_application_display_name(application_name),
                    expected_label,
                )

    def test_unknown_has_no_label_and_ordinary_application_is_unchanged(self) -> None:
        self.assertIsNone(get_application_display_name(WPS_UNKNOWN))
        self.assertIsNone(get_application_display_name(WINDOWS_SHELL))
        self.assertEqual(get_application_display_name(None), "DEFAULT")
        self.assertEqual(get_application_display_name("CODE.EXE"), "CODE.EXE")

    def test_hud_header_uses_display_label_only_at_presentation_boundary(self) -> None:
        hud = ShortcutHudWindow()
        expected_titles = {
            (WPS_WRITER, "Ctrl"): "WPS Writer · Ctrl",
            (WPS_PDF, "Alt"): "WPS PDF · Alt",
            (WPS_PRESENTATION, "Ctrl+Shift"): "WPS Presentation · Ctrl+Shift",
            (WPS_UNKNOWN, "Win"): "Win",
            ("CODE.EXE", "Ctrl"): "CODE.EXE · Ctrl",
        }
        for (application_name, modifier), expected_title in expected_titles.items():
            with self.subTest(application_name=application_name):
                source = "GLOBAL" if application_name == WPS_UNKNOWN else "APP"
                entry = ShortcutEntry("R", "Run", source)
                hud.set_entries(application_name, modifier, [entry], "en_US")
                self.assertEqual(
                    hud._header_label.text(),
                    expected_title,
                )
        hud.deleteLater()

    def test_string_description_is_displayed_directly(self) -> None:
        self.assertEqual(select_description_text("Save", "zh_CN"), "Save")

    def test_current_language_is_selected_from_description_mapping(self) -> None:
        description = {"en": "Save", "zh": "保存"}

        self.assertEqual(select_description_text(description, "zh_CN"), "保存")
        self.assertEqual(select_description_text(description, "en_US"), "Save")

    def test_missing_language_uses_reasonable_fallback(self) -> None:
        self.assertEqual(
            select_description_text({"en": "Save", "zh": "保存"}, "fr_FR"),
            "Save",
        )
        self.assertEqual(select_description_text({"ja": "保存"}, "fr_FR"), "保存")
        self.assertEqual(select_description_text({}, "zh_CN"), "N/A")

    @staticmethod
    def _key_texts(hud: ShortcutHudWindow) -> list[str]:
        return [
            label.text()
            for label in hud.findChildren(QLabel)
            if label.objectName() == "shortcutHudKey"
        ]

    @staticmethod
    def _global_section_texts(hud: ShortcutHudWindow) -> list[str]:
        return [
            label.text()
            for label in hud.findChildren(QLabel)
            if label.objectName() == "shortcutHudGlobalSectionLabel"
        ]

    def test_visible_groups_limit_local_and_pin_all_global_entries(self) -> None:
        entries = [
            ShortcutEntry(str(index), f"Local {index}", "APP")
            for index in range(10)
        ] + [
            ShortcutEntry("Tab", "Switch windows", "GLOBAL"),
            ShortcutEntry("F4", "Close current window", "GLOBAL"),
        ]

        local_entries, global_entries = select_visible_entry_groups(entries, 8)

        self.assertEqual([entry.key for entry in local_entries], list("01234567"))
        self.assertEqual([entry.key for entry in global_entries], ["Tab", "F4"])

    def test_user_entries_do_not_consume_builtin_local_quota(self) -> None:
        for user_count in (1, 2):
            with self.subTest(user_count=user_count):
                entries = [
                    ShortcutEntry(f"F{13 + index}", "User", "USER_APP")
                    for index in range(user_count)
                ] + [
                    ShortcutEntry(str(index), "Built-in", "APP")
                    for index in range(8)
                ]

                local_entries, global_entries = select_visible_entry_groups(entries, 8)

                self.assertEqual(
                    [entry.source for entry in local_entries],
                    ["USER_APP"] * user_count + ["APP"] * 8,
                )
                self.assertEqual(len(local_entries), user_count + 8)
                self.assertEqual(global_entries, [])

    def test_chrome_and_edge_keep_two_user_plus_nine_builtin_entries(self) -> None:
        entries = [
            ShortcutEntry("F13", "User 1", "USER_APP"),
            ShortcutEntry("F14", "User 2", "USER_APP"),
            *[
                ShortcutEntry(str(index), "Built-in", "APP")
                for index in range(9)
            ],
        ]

        for application_name in ("CHROME.EXE", "MSEDGE.EXE"):
            with self.subTest(application_name=application_name):
                local_entries, global_entries = select_visible_entry_groups(
                    entries,
                    get_hud_entry_limit(application_name, "Ctrl"),
                )

                self.assertEqual(
                    [entry.source for entry in local_entries],
                    ["USER_APP"] * 2 + ["APP"] * 9,
                )
                self.assertEqual(global_entries, [])

    def test_user_override_conflict_is_deduplicated_before_builtin_quota(self) -> None:
        built_in_keys = ["P", "`", "/", "B", "G", "H", "Enter", "L"]
        entries = resolve_shortcuts(
            {
                "CODE.EXE": {
                    "Ctrl": {key: f"Built-in {key}" for key in built_in_keys}
                },
                "GLOBAL": {},
            },
            "CODE.EXE",
            "Ctrl",
            {
                "CODE.EXE": {
                    "shortcuts": {
                        "Ctrl": {"p": {"en": "User P", "zh": "用户 P"}}
                    }
                }
            },
        )

        local_entries, global_entries = select_visible_entry_groups(entries, 8)

        self.assertEqual([entry.key.casefold() for entry in local_entries].count("p"), 1)
        self.assertEqual(local_entries[0].source, "USER_APP")
        self.assertEqual(
            [entry.source for entry in local_entries],
            ["USER_APP"] + ["APP"] * 7,
        )
        self.assertEqual(global_entries, [])

    def test_user_entries_are_extra_while_global_entries_remain_pinned(self) -> None:
        entries = [
            ShortcutEntry("F13", "User", "USER_APP"),
            *[
                ShortcutEntry(str(index), "Built-in", "DEFAULT")
                for index in range(10)
            ],
            ShortcutEntry("Tab", "Switch windows", "GLOBAL"),
            ShortcutEntry("F4", "Close", "GLOBAL"),
        ]

        local_entries, global_entries = select_visible_entry_groups(entries, 8)

        self.assertEqual(len(local_entries), 9)
        self.assertEqual(local_entries[0].source, "USER_APP")
        self.assertTrue(all(entry.source == "DEFAULT" for entry in local_entries[1:]))
        self.assertEqual([entry.key for entry in global_entries], ["Tab", "F4"])

    def test_mixed_entries_render_global_section_after_pinned_local_rows(self) -> None:
        hud = ShortcutHudWindow()
        entries = [
            ShortcutEntry(str(index), f"Local {index}", "APP")
            for index in range(10)
        ] + [
            ShortcutEntry("Tab", "Switch windows", "GLOBAL"),
            ShortcutEntry("F4", "Close current window", "GLOBAL"),
        ]

        hud.set_entries("CODE.EXE", "Alt", entries, "zh_CN")

        self.assertEqual(
            self._key_texts(hud),
            list("01234567") + ["Tab", "F4"],
        )
        self.assertEqual(self._global_section_texts(hud), ["全局"])
        self.assertEqual(hud._header_label.text(), "CODE.EXE · Alt")
        hud.deleteLater()

    def test_global_only_shell_and_wps_unknown_have_modifier_only_title(self) -> None:
        entries = [
            ShortcutEntry("Tab", "Switch windows", "GLOBAL"),
            ShortcutEntry("F4", "Close current window", "GLOBAL"),
        ]

        for application_name in (WINDOWS_SHELL, WINDOWS_DESKTOP, WPS_UNKNOWN):
            with self.subTest(application_name=application_name):
                hud = ShortcutHudWindow()
                hud.set_entries(application_name, "Alt", entries, "zh_CN")
                self.assertEqual(hud._header_label.text(), "Alt")
                self.assertEqual(self._global_section_texts(hud), [])
                self.assertEqual(self._key_texts(hud), ["Tab", "F4"])
                hud.deleteLater()

    def test_app_global_conflict_renders_local_winner_only(self) -> None:
        entries = resolve_shortcuts(
            {
                "CODE.EXE": {"Alt": {"F4": "Local close"}},
                "GLOBAL": {
                    "Alt": {
                        "f4": "Global close",
                        "Tab": "Switch windows",
                    }
                },
            },
            "CODE.EXE",
            "Alt",
        )
        hud = ShortcutHudWindow()

        hud.set_entries("CODE.EXE", "Alt", entries, "en_US")

        self.assertEqual(self._key_texts(hud), ["F4", "Tab"])
        descriptions = [
            label.text()
            for label in hud.findChildren(QLabel)
            if label.objectName() == "shortcutHudDescription"
        ]
        self.assertEqual(descriptions, ["Local close", "Switch windows"])
        self.assertEqual(self._global_section_texts(hud), ["全局"])
        hud.deleteLater()

    def test_row_count_changes_keep_bottom_right_anchor(self) -> None:
        hud = ShortcutHudWindow()
        screen = self.qt_application.primaryScreen()
        self.assertIsNotNone(screen)
        available = screen.availableGeometry()

        heights: list[int] = []
        bottom_margins: list[int] = []
        for count in (8, 3, 6):
            entries = [
                ShortcutEntry(str(index), f"Action {index}", "APP")
                for index in range(count)
            ]
            hud.set_entries("CODE.EXE", "Ctrl", entries, "en_US")
            QTest.qWait(30)
            heights.append(hud.height())
            bottom_margins.append(
                available.y()
                + available.height()
                - (hud.y() + hud.height())
            )

        self.assertLess(heights[1], heights[2])
        self.assertLess(heights[2], heights[0])
        self.assertEqual(bottom_margins, [hud.SCREEN_MARGIN] * 3)
        hud.deleteLater()


if __name__ == "__main__":
    unittest.main()
