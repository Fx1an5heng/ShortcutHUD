"""KeyPath stays inside one Full Guide session and owns its mode-local input."""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import Mock

from PySide6.QtCore import Qt, QTranslator
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from scripts.application_descriptor import ApplicationDescriptorFactory
from scripts.full_guide_context import GuideSnapshot
from scripts.full_guide_controller import FullGuideController
from scripts.full_guide_window import FullGuideWindow
from scripts.keypath_model import GuideMode, KeyPathLevel
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.suppression_policy import SuppressionPolicy
from tests.test_full_guide_data import entry

ROOT = Path(__file__).resolve().parents[1]


def keypath_entry(identifier, keys, *, title, category, kind="combo", scope="APP", description=None, order=0):
    return replace(
        entry(identifier, keys, kind=kind, category=category, scope=scope, description=description or {"en": title, "zh_CN": title}),
        title={"en": title},
        order=order,
    )


def test_catalog():
    catalog = ShortcutCatalog([
        keypath_entry("toggle", ("Ctrl", "`"), title="Toggle Integrated Terminal", category="integrated_terminal"),
        keypath_entry("new", ("Ctrl", "Shift", "`"), title="New Integrated Terminal", category="integrated_terminal", order=1),
        keypath_entry("save", ("Ctrl", "S"), title="Save File", category="general", order=2),
        keypath_entry("run", ("F5",), title="Start Debugging", category="debug", kind="single", order=3),
        keypath_entry("bindings", ("Ctrl+K", "Ctrl+S"), title="Keyboard Shortcuts", category="general", kind="sequence", order=4),
        keypath_entry("global", ("Ctrl", "Alt", "G"), title="Global Action", category="global", scope="GLOBAL", order=5),
    ])
    catalog.category_titles = {
        "integrated_terminal": {"en": "Integrated Terminal", "zh_CN": "集成终端"},
        "general": {"en": "General", "zh_CN": "常规"},
        "debug": {"en": "Debug", "zh_CN": "调试"},
    }
    return catalog


def snapshot(identity="SAMPLE.EXE"):
    return GuideSnapshot(ApplicationDescriptorFactory().describe(identity), 123, "DISPLAY2", (0, 0, 1400, 900))


class KeyPathInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def make(self, *, catalog=None, profiles=None, language="en", identity="SAMPLE.EXE"):
        catalog = catalog if catalog is not None else test_catalog()
        view = FullGuideWindow()
        quick_hud = Mock()
        guide = FullGuideController(
            view,
            quick_hud,
            SuppressionPolicy(),
            lambda: snapshot(identity),
            lambda: catalog,
            lambda: profiles or {},
            lambda: language,
        )
        self.addCleanup(view.deleteLater)
        self.addCleanup(view.close)
        guide.toggle()
        view.activateWindow()
        view.raise_()
        self.qt.processEvents()
        return guide, view, quick_hud

    def enter(self, guide, view):
        QTest.keyClick(view.search_box, Qt.Key.Key_Tab)
        self.qt.processEvents()
        self.assertEqual(guide.mode, GuideMode.KEYPATH)
        self.assertEqual(guide.keypath_session.level, KeyPathLevel.ROOT)

    def terminal_category(self, guide):
        return next(category for category in guide.keypath_session.dataset.categories if category.key == "integrated_terminal")

    def test_tab_root_category_result_back_and_escape(self):
        guide, view, _ = self.make()
        self.enter(guide, view)
        terminal = self.terminal_category(guide)
        QTest.keyClick(view, getattr(Qt.Key, f"Key_{terminal.hint}"))
        self.assertEqual(guide.keypath_session.level, KeyPathLevel.CATEGORY)
        action = next(item for item in terminal.actions if item.entry_id == "toggle")
        QTest.keyClick(view, getattr(Qt.Key, f"Key_{action.hint}"))
        self.assertEqual(guide.keypath_session.level, KeyPathLevel.RESULT)
        QTest.keyClick(view, Qt.Key.Key_Backspace)
        self.assertEqual(guide.keypath_session.level, KeyPathLevel.CATEGORY)
        QTest.keyClick(view, Qt.Key.Key_Backspace)
        self.assertEqual(guide.keypath_session.level, KeyPathLevel.ROOT)
        QTest.keyClick(view, Qt.Key.Key_Backspace)
        self.assertEqual(guide.keypath_session.level, KeyPathLevel.ROOT)
        QTest.keyClick(view, Qt.Key.Key_Escape)
        self.assertEqual(guide.mode, GuideMode.NORMAL)
        self.assertTrue(guide.active)

    def test_escape_exits_directly_from_every_keypath_level(self):
        guide, view, _ = self.make()
        for level in (KeyPathLevel.ROOT, KeyPathLevel.CATEGORY, KeyPathLevel.RESULT):
            self.enter(guide, view)
            terminal = self.terminal_category(guide)
            if level != KeyPathLevel.ROOT:
                guide.on_keypath_category(terminal.key)
            if level == KeyPathLevel.RESULT:
                guide.on_keypath_action(terminal.actions[0].entry_id)
            QTest.keyClick(view, Qt.Key.Key_Escape)
            self.assertEqual(guide.mode, GuideMode.NORMAL)
            self.assertTrue(guide.active)

    def test_activation_hotkey_closes_whole_guide_from_keypath(self):
        guide, view, quick_hud = self.make()
        self.enter(guide, view)
        guide.toggle()
        self.assertFalse(guide.active)
        self.assertEqual(guide.mode, GuideMode.NORMAL)
        quick_hud.set_guide_active.assert_called_with(False)

    def test_filter_and_query_define_dataset_and_survive_exit(self):
        guide, view, quick_hud = self.make()
        guide.on_key_event("Ctrl", "down")
        guide.on_key_event("Ctrl", "up")
        view.search_box.setText("terminal")
        self.enter(guide, view)
        actual = tuple(action.entry_id for category in guide.keypath_session.dataset.categories for action in category.actions)
        self.assertEqual(set(actual), {"toggle", "new"})
        QTest.keyClick(view, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertFalse(view.search_box.hasFocus())
        self.assertFalse(view.search_box.isEnabled())
        QTest.keyClick(view, Qt.Key.Key_A)
        self.assertEqual(view.search_box.text(), "terminal")
        guide.on_key_event("Shift", "down")
        guide.on_key_event("Shift", "up")
        self.assertEqual(guide.modifier_filter.selected, ("Ctrl",))
        QTest.keyClick(view, Qt.Key.Key_Escape)
        self.qt.processEvents()
        self.assertEqual(view.search_box.text(), "terminal")
        self.assertEqual(guide.modifier_filter.selected, ("Ctrl",))
        self.assertTrue(view.search_box.hasFocus())
        self.assertTrue(quick_hud.set_guide_active.call_args_list[0].args[0])
        self.assertFalse(any(call.args == (False,) for call in quick_hud.set_guide_active.call_args_list))

    def test_normal_scroll_position_is_restored(self):
        catalog = ShortcutCatalog([
            keypath_entry(f"item-{index}", ("Ctrl", f"K{index}"), title=f"Item {index}", category="general", order=index)
            for index in range(80)
        ])
        guide, view, _ = self.make(catalog=catalog)
        view.resize(620, 400)
        QTest.qWait(100)
        bar = view.scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        expected = min(120, bar.maximum())
        bar.setValue(expected)
        self.enter(guide, view)
        QTest.keyClick(view, Qt.Key.Key_Escape)
        QTest.qWait(10)
        self.assertEqual(bar.value(), expected)

    def test_root_category_result_rendering_mouse_and_no_horizontal_scroll(self):
        guide, view, _ = self.make()
        self.enter(guide, view)
        category_rows = view.keypath_panel.findChildren(QFrame, "keypathCategoryRow")
        terminal_row = next(row for row in category_rows if row.identity == "integrated_terminal")
        self.assertIn("[T]", [label.text() for label in terminal_row.findChildren(QLabel)])
        QTest.mouseClick(terminal_row, Qt.MouseButton.LeftButton)
        self.qt.processEvents()
        self.assertEqual(guide.keypath_session.level, KeyPathLevel.CATEGORY)
        action_rows = view.keypath_panel.findChildren(QFrame, "keypathActionRow")
        toggle_row = next(row for row in action_rows if row.identity == "toggle")
        self.assertIn("Ctrl+`", [label.text() for label in toggle_row.findChildren(QLabel)])
        QTest.mouseClick(toggle_row, Qt.MouseButton.LeftButton)
        self.qt.processEvents()
        trigger = view.keypath_panel.findChild(QLabel, "keypathResultTrigger")
        self.assertEqual(trigger.text(), "Ctrl+`")
        self.assertGreater(max(trigger.font().pointSize(), trigger.font().pixelSize()), 20)
        self.assertEqual(view.keypath_panel.horizontalScrollBar().maximum(), 0)

    def test_empty_dataset_has_friendly_state(self):
        guide, view, _ = self.make(catalog=ShortcutCatalog(), identity="UNKNOWN.EXE")
        self.enter(guide, view)
        empty = view.keypath_panel.findChild(QLabel, "keypathEmpty")
        self.assertIsNotNone(empty)
        self.assertEqual(empty.text(), "No shortcuts available to navigate")

    def test_english_and_compiled_chinese_ui(self):
        guide, view, _ = self.make(language="en")
        self.assertEqual(view.keypath_entry.text(), "Path navigation")
        guide.close()
        translator = QTranslator()
        self.assertTrue(translator.load(str(ROOT / "i18n/shortcut_overlay_zh_CN.qm")))
        self.qt.installTranslator(translator)
        try:
            guide, view, _ = self.make(language="zh_CN")
            self.assertEqual(view.keypath_entry.text(), "路径导航")
            self.enter(guide, view)
            heading = view.keypath_panel.findChild(QLabel, "keypathLevelTitle")
            self.assertEqual(heading.text(), "路径导航")
            terminal = self.terminal_category(guide)
            self.assertEqual(terminal.title, "集成终端")
        finally:
            self.qt.removeTranslator(translator)


if __name__ == "__main__":
    unittest.main()
