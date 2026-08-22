import unittest

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from scripts.shortcut_hud import ShortcutHudWindow, select_description_text
from scripts.shortcut_resolver import ShortcutEntry


class ShortcutHudPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

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