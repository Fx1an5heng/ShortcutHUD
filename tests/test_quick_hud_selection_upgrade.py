"""Regression coverage for persisted Quick HUD selections across Pack upgrades."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver


def _entry(entry_id: str, key: str, *, recommended: bool = False) -> dict[str, object]:
    return {
        "id": entry_id,
        "trigger": {"kind": "combo", "keys": ["Ctrl", key]},
        "title": {"en": entry_id},
        "description": {"en": entry_id},
        "category": "general",
        "scope": "app",
        "recommended": recommended,
        "rank": 10,
        "provenance": {"title": "Test data", "url": "https://example.test/shortcuts"},
        "visibility": ["quick_hud"],
        "builtin": True,
        "aliases": [],
    }


def _write_pack(directory: Path, entries: list[dict[str, object]]) -> None:
    document = {
        "schema_version": 1,
        "id": "sample-app",
        "product": {"en": "Sample App"},
        "app_identities": ["SAMPLE.EXE"],
        "aliases": [],
        "platforms": ["windows"],
        "locales": ["en"],
        "source": {"title": "Test data", "url": "https://example.test"},
        "coverage": {
            "status": "partial",
            "official_reference_title": "Test data",
            "official_reference_url": "https://example.test",
            "verified_date": "2026-09-07",
        },
        "entries": entries,
    }
    (directory / "sample.json").write_text(json.dumps(document), encoding="utf-8")


def _legacy_catalog() -> ShortcutCatalog:
    return ShortcutCatalog.from_legacy_shortcuts(
        {"SAMPLE.EXE": {"Ctrl": {"S": "Legacy save", "O": "Legacy open"}}}
    )


class QuickHudSelectionUpgradeTests(unittest.TestCase):
    def _upgraded_catalog(self, directory: Path, entries: list[dict[str, object]]) -> ShortcutCatalog:
        _write_pack(directory, entries)
        return _legacy_catalog().with_packs_from(directory)

    def _store(
        self,
        directory: Path,
        selected_ids: list[str] | None,
        app_id: str = "SAMPLE.EXE",
    ) -> QuickHudSelectionStore:
        store = QuickHudSelectionStore(directory / "selection.json")
        if selected_ids is not None:
            store.set_selected_ids(app_id, selected_ids)
            store.save()
            store = QuickHudSelectionStore(store.path)
            store.load()
        return store

    def test_old_explicit_ids_survive_as_exact_aliases_or_retained_legacy_entries(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(root, [_entry("sample.save", "S"), _entry("sample.new", "P", recommended=True)])
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s", "legacy:app:sample.exe:ctrl:o"])

            self.assertEqual(
                store.effective_selected_ids_for("SAMPLE.EXE", catalog.entries),
                frozenset({"sample.save", "legacy:app:sample.exe:ctrl:o"}),
            )
            self.assertCountEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)],
                ["S", "O"],
            )

    def test_renamed_id_uses_deterministic_exact_alias_without_rewriting_selection(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(root, [_entry("sample.save-v2", "S")])
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s"])

            self.assertEqual(store.snapshot(), {"SAMPLE.EXE": ["legacy:app:sample.exe:ctrl:s"]})
            self.assertEqual(
                store.effective_selected_ids_for("SAMPLE.EXE", catalog.entries),
                frozenset({"sample.save-v2"}),
            )
            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)],
                ["S"],
            )

    def test_declared_alias_is_authoritative_for_an_intentional_trigger_change(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            replacement = _entry("sample.save-v3", "N")
            replacement["id_aliases"] = ["legacy:app:sample.exe:ctrl:s"]
            catalog = self._upgraded_catalog(root, [replacement])
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s"])

            self.assertNotIn(
                "legacy:app:sample.exe:ctrl:s",
                {entry.id for entry in catalog.entries},
            )
            self.assertEqual(
                store.effective_selected_ids_for("SAMPLE.EXE", catalog.entries),
                frozenset({"sample.save-v3"}),
            )
            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)],
                ["N"],
            )

    def test_ambiguous_pack_trigger_keeps_explicit_legacy_without_hiding_new_defaults(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(
                root,
                [_entry("sample.first-save", "S", recommended=True), _entry("sample.second-save", "S")],
            )
            configured = self._store(root, ["legacy:app:sample.exe:ctrl:s"])
            never_configured = QuickHudSelectionStore(root / "missing-selection.json")

            self.assertIn(
                "legacy:app:sample.exe:ctrl:s",
                {entry.id for entry in catalog.entries},
            )
            self.assertEqual(
                [item.description for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=configured)],
                ["Legacy save"],
            )
            self.assertEqual(
                [item.description for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=never_configured, language="en")],
                ["sample.first-save"],
            )

    def test_mixed_valid_and_stale_explicit_ids_preserve_only_the_valid_subset(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(root, [_entry("sample.save", "S"), _entry("sample.recommended", "P", recommended=True)])
            store = self._store(root, ["sample.save", "retired:unknown"])

            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)],
                ["S"],
            )

    def test_all_stale_explicit_ids_do_not_fall_back_to_recommended(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(root, [_entry("sample.recommended", "P", recommended=True)])
            store = self._store(root, ["retired:unknown"])

            self.assertEqual(store.effective_selected_ids_for("SAMPLE.EXE", catalog.entries), frozenset())
            self.assertEqual(
                CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store),
                [],
            )

    def test_explicit_empty_selection_remains_empty(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(root, [_entry("sample.recommended", "P", recommended=True)])
            store = self._store(root, [])

            self.assertEqual(
                CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store),
                [],
            )

    def test_missing_selection_uses_recommended_defaults(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(root, [_entry("sample.recommended", "P", recommended=True)])
            store = self._store(root, None)

            self.assertIsNone(store.selected_ids_for("SAMPLE.EXE"))
            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)],
                ["P"],
            )

    def test_recommended_changes_never_mutate_configured_user_output(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(
                root,
                [_entry("sample.save", "S"), _entry("sample.new-recommended", "N", recommended=True)],
            )
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s"])

            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)],
                ["S"],
            )

    def test_current_excel_legacy_selection_upgrades_without_touching_user_config(self) -> None:
        """Use a temporary selection fixture, never the APPDATA selection file."""

        old_excel_ids = [
            "legacy:app:excel.exe:ctrl+shift:$",
            "legacy:app:excel.exe:ctrl:pageup",
            "legacy:app:excel.exe:ctrl+shift:!",
            "legacy:app:excel.exe:ctrl:e",
            "legacy:app:excel.exe:ctrl+shift:+",
            "legacy:app:excel.exe:ctrl:pagedown",
            "legacy:app:excel.exe:ctrl+shift:%3a",
            "legacy:app:excel.exe:ctrl+shift:#",
            "legacy:app:excel.exe:ctrl+shift:l",
            "legacy:app:excel.exe:ctrl+shift:@",
            "legacy:app:excel.exe:ctrl+alt:v",
            "legacy:app:excel.exe:ctrl:t",
            "legacy:app:excel.exe:ctrl:;",
            "legacy:app:excel.exe:ctrl+shift:%",
            "legacy:app:excel.exe:ctrl:1",
            "legacy:app:excel.exe:ctrl:d",
            "legacy:app:excel.exe:ctrl:`",
            "legacy:app:excel.exe:ctrl+alt:f5",
        ]
        project_root = Path(__file__).resolve().parents[1]
        legacy_data = json.loads((project_root / "config" / "shortcuts.json").read_text(encoding="utf-8"))
        catalog = ShortcutCatalog.from_legacy_shortcuts(legacy_data).with_packs_from(project_root / "config" / "shortcut_packs")
        with TemporaryDirectory() as temporary:
            store = self._store(Path(temporary), old_excel_ids, "EXCEL.EXE")
            effective = store.effective_selected_ids_for("EXCEL.EXE", catalog.entries)

        self.assertEqual(len(effective), len(old_excel_ids))
        self.assertIn("microsoft-excel.apply-currency-format", effective)
        self.assertIn("legacy:app:excel.exe:ctrl+shift:l", effective)
        currency = next(entry for entry in catalog.entries if entry.id == "microsoft-excel.apply-currency-format")
        self.assertIn("legacy:app:excel.exe:ctrl+shift:$", currency.id_aliases)

    def test_migration_is_deterministic_and_does_not_touch_real_user_paths(self) -> None:
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            first_root, second_root = Path(first), Path(second)
            first_catalog = self._upgraded_catalog(first_root, [_entry("sample.save-v2", "S")])
            second_catalog = self._upgraded_catalog(second_root, [_entry("sample.save-v2", "S")])
            first_store = self._store(first_root, ["legacy:app:sample.exe:ctrl:s"])
            second_store = self._store(second_root, ["legacy:app:sample.exe:ctrl:s"])

            self.assertEqual(
                first_store.effective_selected_ids_for("SAMPLE.EXE", first_catalog.entries),
                second_store.effective_selected_ids_for("SAMPLE.EXE", second_catalog.entries),
            )
            self.assertTrue(first_store.path.is_relative_to(first_root))
            self.assertTrue(second_store.path.is_relative_to(second_root))


if __name__ == "__main__":
    unittest.main()
