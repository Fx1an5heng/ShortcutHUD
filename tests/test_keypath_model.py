"""KeyPath hint allocation and navigation are pure and deterministic."""
from dataclasses import replace
import unittest

from scripts.full_guide_model import group_entries
from scripts.keypath_model import (
    HintRequest, KeyPathCategory, KeyPathDataset, KeyPathHintAllocator, KeyPathLevel, KeyPathSession,
    build_keypath_dataset,
)
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import resolve_catalog_view
from tests.test_full_guide_data import entry


def keypath_entry(identifier, keys, *, title, category, kind="combo", scope="APP", description=None):
    return replace(
        entry(identifier, keys, kind=kind, category=category, scope=scope, description=description or {"en": title, "zh_CN": title}),
        title={"en": title},
    )


class KeyPathHintAllocatorTests(unittest.TestCase):
    def test_preferred_category_hint_and_collisions_are_distinct(self):
        catalog = ShortcutCatalog([
            keypath_entry("toggle", ("Ctrl", "`"), title="Toggle Integrated Terminal", category="integrated_terminal"),
            keypath_entry("task", ("Ctrl", "B"), title="Tasks", category="tasks"),
        ])
        dataset = build_keypath_dataset(group_entries(resolve_catalog_view(catalog, "SAMPLE.EXE")))
        hints = {category.key: category.hint for category in dataset.categories}
        self.assertEqual(hints["integrated_terminal"], "T")
        self.assertNotEqual(hints["integrated_terminal"], hints["tasks"])

    def test_allocation_is_deterministic_and_independent_of_input_order(self):
        requests = (
            HintRequest("toggle-terminal", sources=("Toggle Terminal",)),
            HintRequest("toggle-panel", sources=("Toggle Panel",)),
            HintRequest("toggle-sidebar", sources=("Toggle Sidebar",)),
        )
        allocator = KeyPathHintAllocator()
        expected = allocator.allocate(requests)
        self.assertEqual(expected, allocator.allocate(tuple(reversed(requests))))
        self.assertEqual(len(set(expected.values())), len(expected))

    def test_chinese_only_item_receives_alphanumeric_fallback(self):
        result = KeyPathHintAllocator().allocate((HintRequest("用户动作", sources=("我的特殊动作",)),))
        self.assertEqual(result["用户动作"], "1")

    def test_overflow_uses_uniform_multi_character_hints_without_crashing(self):
        requests = tuple(HintRequest(f"item-{index}", sources=("Item",)) for index in range(80))
        hints = KeyPathHintAllocator().allocate(requests)
        self.assertEqual(len(hints), 80)
        self.assertEqual(len(set(hints.values())), 80)
        self.assertEqual({len(hint) for hint in hints.values()}, {2})


class KeyPathDatasetAndStateTests(unittest.TestCase):
    def make_dataset(self):
        catalog = ShortcutCatalog([
            keypath_entry("toggle", ("Ctrl", "`"), title="Toggle Integrated Terminal", category="integrated_terminal", description={"en": "Show or hide the integrated terminal", "zh_CN": "显示或隐藏集成终端"}),
            keypath_entry("new", ("Ctrl", "Shift", "`"), title="New Integrated Terminal", category="integrated_terminal"),
            keypath_entry("run", ("F5",), title="Start Debugging", category="debug", kind="single"),
            keypath_entry("bindings", ("Ctrl+K", "Ctrl+S"), title="Keyboard Shortcuts", category="general", kind="sequence"),
            keypath_entry("tap", ("Shift",), title="Sticky Selection", category="general", kind="double_tap"),
            keypath_entry("global", ("Ctrl", "Alt", "G"), title="Global Action", category="global", scope="GLOBAL"),
        ])
        rows = resolve_catalog_view(catalog, "SAMPLE.EXE", language="zh_CN")
        return build_keypath_dataset(group_entries(rows))

    def test_root_category_result_and_back_navigation(self):
        session = KeyPathSession(self.make_dataset())
        terminal = next(category for category in session.dataset.categories if category.key == "integrated_terminal")
        toggle = next(action for action in terminal.actions if action.entry_id == "toggle")
        self.assertEqual(session.level, KeyPathLevel.ROOT)
        self.assertTrue(session.select_hint(terminal.hint))
        self.assertEqual(session.level, KeyPathLevel.CATEGORY)
        self.assertTrue(session.select_hint(toggle.hint))
        self.assertEqual(session.level, KeyPathLevel.RESULT)
        self.assertEqual(session.result.trigger, "Ctrl+`")
        self.assertTrue(session.back())
        self.assertEqual(session.level, KeyPathLevel.CATEGORY)
        self.assertTrue(session.back())
        self.assertEqual(session.level, KeyPathLevel.ROOT)
        self.assertFalse(session.back())

    def test_complete_catalog_trigger_types_and_global_are_navigable(self):
        dataset = self.make_dataset()
        actions = [action for category in dataset.categories for action in category.actions]
        self.assertEqual({action.entry_id for action in actions}, {"toggle", "new", "run", "bindings", "tap", "global"})
        self.assertIn("F5", [action.trigger for action in actions])
        self.assertIn("Ctrl+K Ctrl+S", [action.trigger for action in actions])
        self.assertIn("Shift × 2", [action.trigger for action in actions])
        self.assertIn("global", [category.key for category in dataset.categories])

    def test_keypath_keeps_resolver_precedence_and_deduplication(self):
        catalog = ShortcutCatalog([
            keypath_entry("app-save", ("Ctrl", "S"), title="Application Save", category="general"),
            keypath_entry("global-save", ("Ctrl", "S"), title="Global Save", category="global", scope="GLOBAL"),
            keypath_entry("global-open", ("Ctrl", "O"), title="Global Open", category="global", scope="GLOBAL"),
        ])
        profiles = {"SAMPLE.EXE": {"shortcuts": {"Ctrl": {"S": "My Save"}}}}
        rows = resolve_catalog_view(catalog, "SAMPLE.EXE", profiles)
        dataset = build_keypath_dataset(group_entries(rows))
        actions = [action for category in dataset.categories for action in category.actions]
        self.assertEqual([(action.trigger, action.row.source) for action in actions], [("Ctrl+S", "USER_APP"), ("Ctrl+O", "GLOBAL")])

    def test_user_app_entry_is_included_even_with_chinese_description(self):
        profiles = {"SAMPLE.EXE": {"shortcuts": {"Ctrl+Alt": {"M": "我的特殊动作"}}}}
        rows = resolve_catalog_view(ShortcutCatalog(), "SAMPLE.EXE", profiles, "zh_CN")
        dataset = build_keypath_dataset(group_entries(rows))
        self.assertEqual(dataset.entry_count, 1)
        self.assertEqual(dataset.categories[0].actions[0].label, "我的特殊动作")

    def test_two_character_hint_waits_for_complete_selection(self):
        requests = tuple(HintRequest(f"category-{index}") for index in range(40))
        hints = KeyPathHintAllocator().allocate(requests)
        categories = tuple(KeyPathCategory(request.stable_id, hints[request.stable_id], request.stable_id, ()) for request in requests)
        session = KeyPathSession(KeyPathDataset(categories))
        target = categories[0]
        self.assertTrue(session.select_hint(target.hint[0]))
        self.assertEqual(session.level, KeyPathLevel.ROOT)
        self.assertEqual(session.input_buffer, target.hint[0])
        self.assertTrue(session.select_hint(target.hint[1]))
        self.assertEqual(session.category_key, target.key)


if __name__ == "__main__":
    unittest.main()
