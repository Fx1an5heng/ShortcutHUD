import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.config_manager import ConfigManager
from scripts.shortcut_catalog import (
    CatalogValidationError,
    ShortcutCatalog,
    parse_shortcut_pack,
    select_catalog_text,
)
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver
from scripts.shortcut_resolver import resolve_shortcuts


def _pack(*, entries=None, aliases=None):
    return {
        "schema_version": 1,
        "id": "sample.pack",
        "product": {"en": "Sample", "zh_CN": "示例"},
        "app_identities": ["SAMPLE.EXE"],
        "aliases": aliases or ["SAMPLE-ALIAS.EXE"],
        "platforms": ["windows"],
        "locales": ["en", "zh_CN"],
        "source": {"title": "Official docs", "url": "https://example.test/docs"},
        "coverage": {"status": "partial", "official_reference_title": "Official docs", "official_reference_url": "https://example.test/docs", "verified_date": "2026-09-07"},
        "entries": entries if entries is not None else [
            {
                "id": "sample.save",
                "trigger": {"kind": "combo", "keys": ["Ctrl", "S"]},
                "title": {"en": "Save", "zh_CN": "保存"},
                "description": {"en": "Save document", "zh_CN": "保存文档"},
                "category": "file",
                "scope": "app",
                "recommended": True,
                "rank": 10,
                "provenance": {"title": "Official docs", "url": "https://example.test/save"},
                "visibility": ["quick_hud", "full_guide"],
                "builtin": True,
                "aliases": ["save"],
            }
        ],
    }


class ShortcutCatalogTests(unittest.TestCase):
    def test_legacy_adapter_preserves_resolver_results_and_stable_ids(self) -> None:
        legacy = {
            "CODE.EXE": {"Ctrl": {"S": {"en": "Save", "zh": "保存"}, "P": "Open"}},
            "DEFAULT": {"Ctrl": {"C": "Copy"}},
            "GLOBAL": {"Ctrl": {"P": "Palette", "G": "Global"}},
        }
        catalog = ShortcutCatalog.from_legacy_shortcuts(legacy)
        resolver = CatalogShortcutResolver(catalog)

        self.assertEqual(
            resolver.resolve("CODE.EXE", "Ctrl"),
            resolve_shortcuts(legacy, "CODE.EXE", "Ctrl"),
        )
        self.assertEqual(
            [entry.id for entry in catalog.entries][:2],
            ["legacy:app:code.exe:ctrl:s", "legacy:app:code.exe:ctrl:p"],
        )
        self.assertEqual(catalog.entries[0].title["zh_CN"], "保存")

    def test_user_layer_hidden_builtin_and_global_conflict_remain_compatible(self) -> None:
        legacy = {"CODE.EXE": {"Ctrl": {"P": "Builtin", "B": "Browse"}}, "GLOBAL": {"Ctrl": {"P": "Global", "G": "Global"}}}
        profiles = {"CODE.EXE": {"shortcuts": {"Ctrl": {"P": "User"}}, "hidden_builtin": {"Ctrl": ["B"]}}}
        resolved = CatalogShortcutResolver(ShortcutCatalog.from_legacy_shortcuts(legacy)).resolve("CODE.EXE", "Ctrl", profiles)

        self.assertEqual([(item.key, item.description, item.source) for item in resolved], [("P", "User", "USER_APP"), ("G", "Global", "GLOBAL")])

    def test_pack_has_structured_future_trigger_kinds_but_runtime_uses_combo_only(self) -> None:
        document = _pack(entries=[
            {**_pack()["entries"][0], "id": "sample.combo"},
            {**_pack()["entries"][0], "id": "sample.sequence", "trigger": {"kind": "sequence", "keys": ["Ctrl+K", "Ctrl+S"]}},
            {**_pack()["entries"][0], "id": "sample.double", "trigger": {"kind": "double_tap", "keys": ["Shift"]}},
        ])
        pack = parse_shortcut_pack(document)
        self.assertEqual([entry.trigger.kind for entry in pack.entries], ["combo", "sequence", "double_tap"])
        catalog = ShortcutCatalog(pack.entries)
        self.assertEqual([entry.key for entry in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl")], ["S"])

    def test_pack_alias_identity_matches_same_catalog_entries(self) -> None:
        pack = parse_shortcut_pack(_pack())
        entries = CatalogShortcutResolver(ShortcutCatalog(pack.entries)).resolve("sample-alias.exe", "Ctrl")
        self.assertEqual([entry.key for entry in entries], ["S"])

    def test_recommended_defaults_and_rank_have_deterministic_hud_order(self) -> None:
        first = _pack()["entries"][0]
        lower_rank = {**first, "id": "sample.open", "trigger": {"kind": "combo", "keys": ["Ctrl", "O"]}, "rank": 1}
        hidden_default = {**first, "id": "sample.hidden", "trigger": {"kind": "combo", "keys": ["Ctrl", "H"]}, "recommended": False, "rank": 0}
        catalog = ShortcutCatalog(parse_shortcut_pack(_pack(entries=[first, lower_rank, hidden_default])).entries)
        self.assertEqual(
            [entry.key for entry in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl")],
            ["O", "S"],
        )

    def test_localization_has_language_then_english_fallback(self) -> None:
        self.assertEqual(select_catalog_text({"en": "Save", "zh_CN": "保存"}, "zh_TW"), "保存")
        self.assertEqual(select_catalog_text({"en": "Save", "zh_CN": "保存"}, "fr_FR"), "Save")

    def test_invalid_pack_is_rejected_for_bad_provenance_and_duplicate_ids(self) -> None:
        invalid = _pack()
        invalid["source"] = {"title": "Docs", "url": "file:///not-safe"}
        with self.assertRaises(CatalogValidationError):
            parse_shortcut_pack(invalid)
        duplicate = _pack(entries=[_pack()["entries"][0], _pack()["entries"][0]])
        with self.assertRaises(CatalogValidationError):
            parse_shortcut_pack(duplicate)

    def test_unsupported_pack_schema_is_rejected(self) -> None:
        invalid = _pack()
        invalid["schema_version"] = 999
        with self.assertRaises(CatalogValidationError):
            parse_shortcut_pack(invalid)

    def test_pack_requires_structured_coverage_metadata(self) -> None:
        invalid = _pack(); invalid.pop("coverage")
        with self.assertRaises(CatalogValidationError):
            parse_shortcut_pack(invalid)

    def test_directory_loader_is_deterministic_and_skips_invalid_files(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            late = _pack()
            late["id"] = "z.pack"
            late["entries"][0]["id"] = "z.save"
            early = _pack()
            early["id"] = "a.pack"
            early["entries"][0]["id"] = "a.save"
            (root / "z.json").write_text(json.dumps(late), encoding="utf-8")
            (root / "a.json").write_text(json.dumps(early), encoding="utf-8")
            (root / "broken.json").write_text("{", encoding="utf-8")
            catalog = ShortcutCatalog.load_packs(root)
            self.assertEqual([entry.id for entry in catalog.entries], ["a.save", "z.save"])
            self.assertEqual(len(catalog.load_issues), 1)

    def test_duplicate_pack_id_is_rejected_without_losing_first_valid_pack(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = _pack()
            second = _pack()
            second["entries"][0]["id"] = "sample.second"
            (root / "a.json").write_text(json.dumps(first), encoding="utf-8")
            (root / "b.json").write_text(json.dumps(second), encoding="utf-8")
            catalog = ShortcutCatalog.load_packs(root)
            self.assertEqual([entry.id for entry in catalog.entries], ["sample.save"])
            self.assertEqual(len(catalog.load_issues), 1)

    def test_selection_is_separate_persistent_state_and_overrides_recommended_default(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "selection.json"
            store = QuickHudSelectionStore(path)
            store.set_selected_ids("SAMPLE.EXE", ["sample.save"])
            store.save()
            loaded = QuickHudSelectionStore(path)
            loaded.load()
            self.assertEqual(loaded.selected_ids_for("sample.exe"), frozenset({"sample.save"}))
            self.assertTrue(loaded.clear_selection("SAMPLE.EXE"))
            self.assertIsNone(loaded.selected_ids_for("SAMPLE.EXE"))

    def test_explicit_selection_filters_effective_hud_entries(self) -> None:
        catalog = ShortcutCatalog(parse_shortcut_pack(_pack()).entries)
        with TemporaryDirectory() as directory:
            store = QuickHudSelectionStore(Path(directory) / "selection.json")
            store.set_selected_ids("SAMPLE.EXE", [])
            self.assertEqual(CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store), [])

    def test_corrupt_legacy_config_falls_back_to_builtin_catalog(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shortcuts_path = root / "shortcuts.json"
            shortcuts_path.write_text("{", encoding="utf-8")
            manager = ConfigManager(str(shortcuts_path), str(root / "settings.json"))
            manager.initialize_configs()
            self.assertTrue(manager.get_shortcut_catalog().entries)
            self.assertEqual(
                [entry.key for entry in CatalogShortcutResolver(manager.get_shortcut_catalog()).resolve("NOTEPAD.EXE", "Ctrl")],
                ["S", "O", "N"],
            )


if __name__ == "__main__":
    unittest.main()
