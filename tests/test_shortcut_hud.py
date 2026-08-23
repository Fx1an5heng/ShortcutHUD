import unittest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from scripts.application_display_names import get_application_display_name
from scripts.shortcut_hud import ShortcutHudWindow, select_description_text
from scripts.shortcut_resolver import ShortcutEntry
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
        self.assertEqual(get_application_display_name(None), "DEFAULT")
        self.assertEqual(get_application_display_name("CODE.EXE"), "CODE.EXE")

    def test_hud_header_uses_display_label_only_at_presentation_boundary(self) -> None:
        hud = ShortcutHudWindow()
        entry = ShortcutEntry("R", "Run", "GLOBAL")
        expected_titles = {
            (WPS_WRITER, "Ctrl"): "WPS Writer · Ctrl",
            (WPS_PDF, "Alt"): "WPS PDF · Alt",
            (WPS_PRESENTATION, "Ctrl+Shift"): "WPS Presentation · Ctrl+Shift",
            (WPS_UNKNOWN, "Win"): "Win",
            ("CODE.EXE", "Ctrl"): "CODE.EXE · Ctrl",
        }
        for (application_name, modifier), expected_title in expected_titles.items():
            with self.subTest(application_name=application_name):
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