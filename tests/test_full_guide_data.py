"""All-trigger, localized read-only Catalog queries and balanced layout."""
from pathlib import Path
from dataclasses import replace
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtWidgets import QApplication

from scripts.full_guide_model import balance_categories, choose_layout_density, column_count_for_width, group_entries
from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.shortcut_catalog import CatalogEntry, CatalogTrigger, ShortcutCatalog
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver, resolve_catalog_view
from scripts.catalog_presentation_dedup import presentation_groups
from scripts.shortcut_library_dialog import ShortcutLibraryModel

ROOT = Path(__file__).resolve().parents[1]


def entry(identifier="save", keys=("Ctrl", "S"), *, kind="combo", category="editing", scope="APP", description=None, recommended=False):
    return CatalogEntry(identifier, CatalogTrigger(kind, keys), {"en": identifier}, description or {"en": "Save file", "zh_CN": "保存文件"}, category, scope, ("SAMPLE.EXE",) if scope == "APP" else (), recommended, 0, {"kind": "pack"}, frozenset({"full_guide"}), True, ("write",), 0)


class GuideDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])
        cls.catalog = ShortcutCatalog.load_packs(ROOT / "config/shortcut_packs")

    def test_all_trigger_kinds_visible_without_quick_hud_eligibility(self):
        catalog = ShortcutCatalog([entry(), entry("run", ("F5",), kind="single"), entry("bindings", ("Ctrl+K", "Ctrl+S"), kind="sequence"), entry("tap", ("Shift",), kind="double_tap")])
        rows = resolve_catalog_view(catalog, "SAMPLE.EXE")
        self.assertEqual({row.entry.trigger.kind for row in rows}, {"single", "combo", "sequence", "double_tap"})
        self.assertIn("F5", [row.trigger for row in rows])
        self.assertIn("Ctrl+K Ctrl+S", [row.trigger for row in rows])
        self.assertIn("Shift × 2", [row.trigger for row in rows])

    def test_shipping_vscode_raw_133_records_resolve_to_95_commands(self):
        entries = [e for e in self.catalog.entries if "CODE.EXE" in e.application_ids]
        rows = resolve_catalog_view(self.catalog, "CODE.EXE")
        self.assertEqual(len(entries), 133)
        self.assertEqual(len(rows), 95)
        self.assertEqual([row.trigger for row in rows].count("Ctrl+K Ctrl+S"), 1)
        self.assertEqual([row.trigger for row in rows].count("F11"), 2)
        self.assertIn("F5", [row.trigger for row in rows])

    def test_all_shipping_catalog_only_entries_survive(self):
        for app in self.catalog.application_titles:
            expected = {e.id for e in self.catalog.entries if app in e.application_ids and not e.trigger.is_quick_hud_eligible()}
            groups = presentation_groups([e for e in self.catalog.entries if app in e.application_ids], app)
            visible = {r.entry.id for r in resolve_catalog_view(self.catalog, app)}
            represented = {member.id for preferred, members in groups if preferred.id in visible for member in members}
            self.assertTrue(expected <= represented, app)

    def test_localization_matches_center_and_hud(self):
        with TemporaryDirectory() as temporary:
            store = QuickHudSelectionStore(Path(temporary) / "selection.json")
            for language in ("zh_CN", "en_US"):
                rows = resolve_catalog_view(self.catalog, "CODE.EXE", language=language)
                selected = next(r for r in rows if r.entry.id == "vscode.quick-open")
                center = next(r for r in ShortcutLibraryModel(self.catalog, store, language=language).rows("CODE.EXE") if r.entry.id == selected.entry.id)
                hud = next(r for r in CatalogShortcutResolver(self.catalog).resolve("CODE.EXE", "Ctrl", language=language) if r.key == "P")
                self.assertEqual(selected.description, center.description)
                self.assertEqual(selected.description, hud.description)
                self.assertEqual(selected.description, "按名称打开文件" if language == "zh_CN" else "Open a file by name")

    def test_categories_localized_and_english_fallback(self):
        rows = resolve_catalog_view(self.catalog, "CODE.EXE", language="zh_CN")
        self.assertTrue(any("编辑" in r.category_title for r in rows))
        fallback = resolve_catalog_view(ShortcutCatalog([entry(description={"en": "English only"})]), "SAMPLE.EXE", language="zh_CN")
        self.assertEqual(fallback[0].description, "English only")

    def test_search_trigger_english_chinese_alias_and_category(self):
        rows = resolve_catalog_view(self.catalog, "CODE.EXE", language="zh_CN")
        for query in ("terminal", "终端", "Ctrl+K", "保存", "导航"):
            self.assertTrue(group_entries(rows, query), query)
        self.assertTrue(group_entries(resolve_catalog_view(ShortcutCatalog([entry()]), "SAMPLE.EXE"), "write"))

    def test_query_clear_restores_deterministic_groups(self):
        rows = resolve_catalog_view(self.catalog, "CODE.EXE", language="zh_CN")
        original = group_entries(rows)
        self.assertFalse(group_entries(rows, "no-such-action-ever"))
        self.assertEqual(group_entries(rows, ""), original)

    def test_no_recommended_duplication(self):
        rows = resolve_catalog_view(self.catalog, "CODE.EXE")
        shown = [r for s in group_entries(rows) for r in s.rows]
        self.assertEqual(len(shown), len({r.entry.id for r in shown}))

    def test_user_wins_app_and_app_wins_global(self):
        catalog = ShortcutCatalog([entry(), entry("global", scope="GLOBAL"), entry("global-open", ("Ctrl", "O"), scope="GLOBAL")])
        profile = {"SAMPLE.EXE": {"shortcuts": {"Ctrl": {"S": "My save"}}}}
        rows = resolve_catalog_view(catalog, "SAMPLE.EXE", profile)
        self.assertEqual([(r.trigger, r.source) for r in rows], [("Ctrl+S", "USER_APP"), ("Ctrl+O", "GLOBAL")])
        self.assertEqual(resolve_catalog_view(catalog, "SAMPLE.EXE")[0].source, "APP")

    def test_hidden_builtin_and_user_only(self):
        profiles = {"SAMPLE.EXE": {"shortcuts": {"Alt": {"U": "Mine"}}, "hidden_builtin": {"Ctrl": ["S"]}}}
        rows = resolve_catalog_view(ShortcutCatalog([entry()]), "SAMPLE.EXE", profiles)
        self.assertEqual([r.trigger for r in rows], ["Alt+U"])
        self.assertEqual(resolve_catalog_view(ShortcutCatalog(), "SAMPLE.EXE", profiles)[0].source, "USER_APP")

    def test_unknown_empty_does_not_reuse_other_app_or_default(self):
        catalog = ShortcutCatalog([entry(), entry("default", scope="DEFAULT")])
        self.assertFalse(resolve_catalog_view(catalog, "UNKNOWN.EXE"))
        self.assertEqual(resolve_catalog_view(catalog, "UNKNOWN.EXE", include_default=True)[0].source, "DEFAULT")

    def test_legacy_duplicate_prefers_pack_but_non_duplicate_survives(self):
        catalog = ShortcutCatalog.from_legacy_shortcuts({"SAMPLE.EXE": {"Ctrl": {"S": "Old", "X": "Extra"}}})
        catalog.entries += (replace(entry(), provenance={"kind": "pack", "presentation_legacy_titles": ["Old"]}),)
        rows = resolve_catalog_view(catalog, "SAMPLE.EXE")
        self.assertEqual([r.entry.id for r in rows if r.trigger == "Ctrl+S"], ["save"])
        self.assertIn("Ctrl+X", [r.trigger for r in rows])

    def test_selection_untouched_independent_of_empty_stale_and_order(self):
        with TemporaryDirectory() as temporary:
            for ids in ([], ["stale"], ["vscode.toggle-terminal", "vscode.quick-open"]):
                store = QuickHudSelectionStore(Path(temporary) / "selection.json")
                store.set_selected_ids("CODE.EXE", ids)
                store.save()
                before = store.path.read_bytes()
                rows = resolve_catalog_view(self.catalog, "CODE.EXE")
                group_entries(rows, "terminal")
                self.assertEqual(len(rows), 95)
                self.assertEqual(store.path.read_bytes(), before)

    def test_large_dataset_balancer_deterministic(self):
        catalog = ShortcutCatalog([entry(f"item{i}", (f"F{i}",), kind="single", category=f"category{i % 13}") for i in range(300)])
        sections = group_entries(resolve_catalog_view(catalog, "SAMPLE.EXE"))
        columns = balance_categories(sections, 5)
        self.assertEqual(columns, balance_categories(sections, 5))
        self.assertEqual(sum(len(s.rows) for c in columns for s in c), 300)
        heights = [sum(s.estimated_height for s in c) for c in columns]
        self.assertLessEqual(max(heights) - min(heights), max(s.estimated_height for s in sections))
        self.assertEqual([column_count_for_width(w) for w in (1080, 1440, 1800)], [3, 4, 5])

    def test_one_screen_density_is_deterministic_and_large_data_scrolls(self):
        vscode = group_entries(resolve_catalog_view(self.catalog, "CODE.EXE", language="zh_CN"))
        first = choose_layout_density(vscode, 1856, 1080)
        self.assertEqual(first, choose_layout_density(vscode, 1856, 1080))
        self.assertIn(first.columns, (5, 6))
        self.assertTrue(first.expected_to_fit)
        large = tuple(replace(section, rows=section.rows * 4) for section in vscode)
        fallback = choose_layout_density(large, 1856, 1080)
        self.assertEqual(fallback.columns, 6)
        self.assertFalse(fallback.expected_to_fit)


if __name__ == "__main__":
    unittest.main()
