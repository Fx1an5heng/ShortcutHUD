from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver
from scripts.shortcut_library_dialog import ShortcutLibraryModel


_PACK_DIRECTORY = Path(__file__).resolve().parents[1] / "config" / "shortcut_packs"


class ShortcutLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ShortcutCatalog.load_packs(_PACK_DIRECTORY)
        self.temp = TemporaryDirectory()
        self.store = QuickHudSelectionStore(Path(self.temp.name) / "selection.json")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_vscode_pilot_pack_loads_with_unique_stable_ids_and_source(self) -> None:
        entries = self.catalog.entries
        self.assertGreaterEqual(len(entries), 40)
        self.assertEqual(len({entry.id for entry in entries}), len(entries))
        self.assertTrue(all(entry.provenance["url"].startswith("https://code.visualstudio.com/") for entry in entries))

    def test_library_application_list_and_localized_rows(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="zh_CN")
        self.assertIn(("CODE.EXE", "Visual Studio Code"), model.applications())
        rows = model.rows("CODE.EXE")
        self.assertGreaterEqual(len(rows), 40)
        terminal = next(row for row in rows if row.entry.id == "vscode.toggle-terminal")
        self.assertEqual(terminal.description, "显示或隐藏集成终端")

    def test_library_searches_trigger_descriptions_aliases_and_category(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="zh_CN")
        self.assertEqual([row.entry.id for row in model.rows("CODE.EXE", "Ctrl+`")], ["vscode.toggle-terminal"])
        self.assertIn("vscode.find-in-files", [row.entry.id for row in model.rows("CODE.EXE", "workspace files")])
        self.assertIn("vscode.toggle-terminal", [row.entry.id for row in model.rows("CODE.EXE", "集成终端")])
        self.assertIn("vscode.show-source-control", [row.entry.id for row in model.rows("CODE.EXE", "git")])
        self.assertIn("vscode.save", [row.entry.id for row in model.rows("CODE.EXE", "File management")])

    def test_no_preference_uses_recommended_and_explicit_empty_is_distinct(self) -> None:
        legacy = {"CODE.EXE": {"Ctrl": {"P": "Open"}}, "GLOBAL": {"Ctrl": {"G": "Global"}}}
        catalog = ShortcutCatalog.from_legacy_shortcuts(legacy)
        resolver = CatalogShortcutResolver(catalog)
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=self.store)], ["P", "G"])
        self.store.set_selected_ids("CODE.EXE", [])
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=self.store)], ["G"])
        self.store.clear_selection("CODE.EXE")
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=self.store)], ["P", "G"])

    def test_selection_persists_and_invalid_ids_fail_safe(self) -> None:
        self.store.set_selected_ids("CODE.EXE", ["vscode.open-file", "stale.id"])
        self.store.save()
        reloaded = QuickHudSelectionStore(self.store.path)
        reloaded.load()
        resolver = CatalogShortcutResolver(self.catalog)
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=reloaded)], ["O"])

    def test_declared_legacy_id_alias_migrates_selection(self) -> None:
        self.store.set_selected_ids("CODE.EXE", ["legacy:app:code.exe:ctrl:s"])
        resolved = CatalogShortcutResolver(self.catalog).resolve("CODE.EXE", "Ctrl", selection_store=self.store)
        self.assertEqual([entry.key for entry in resolved], ["S"])

    def test_model_checkbox_clear_and_restore_recommended(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="en_US")
        self.assertTrue(next(row for row in model.rows("CODE.EXE") if row.entry.id == "vscode.quick-open").checked)
        model.set_checked("CODE.EXE", "vscode.open-file", True)
        self.assertTrue(next(row for row in model.rows("CODE.EXE") if row.entry.id == "vscode.open-file").checked)
        model.clear_all("CODE.EXE")
        self.assertFalse(any(row.checked for row in model.rows("CODE.EXE")))
        model.restore_recommended("CODE.EXE")
        self.assertTrue(next(row for row in model.rows("CODE.EXE") if row.entry.id == "vscode.quick-open").checked)

    def test_user_shortcut_is_part_of_same_library_and_keeps_hud_precedence(self) -> None:
        profiles = {"CODE.EXE": {"shortcuts": {"Ctrl": {"P": {"en": "User Open", "zh": "用户打开"}}}}}
        model = ShortcutLibraryModel(self.catalog, self.store, profiles, "zh_CN")
        self.assertEqual(next(row for row in model.rows("CODE.EXE") if row.entry.id.startswith("user:")).source, "USER_APP")
        resolved = CatalogShortcutResolver(self.catalog).resolve("CODE.EXE", "Ctrl", profiles, self.store)
        self.assertEqual(resolved[0].description["en"], "User Open")


if __name__ == "__main__":
    unittest.main()
