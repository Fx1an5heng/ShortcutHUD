"""Regression coverage for persisted Quick HUD selections across Pack upgrades."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver
from scripts.shortcut_library_dialog import ShortcutLibraryModel


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


def _write_pack(
    directory: Path,
    entries: list[dict[str, object]],
    *,
    app_identities: list[str] | None = None,
    aliases: list[str] | None = None,
) -> None:
    document = {
        "schema_version": 1,
        "id": "sample-app",
        "product": {"en": "Sample App"},
        "app_identities": app_identities or ["SAMPLE.EXE"],
        "aliases": aliases or [],
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
    def _upgraded_catalog(
        self,
        directory: Path,
        entries: list[dict[str, object]],
        *,
        app_identities: list[str] | None = None,
        aliases: list[str] | None = None,
    ) -> ShortcutCatalog:
        _write_pack(directory, entries, app_identities=app_identities, aliases=aliases)
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
                frozenset({"legacy:app:sample.exe:ctrl:s", "legacy:app:sample.exe:ctrl:o"}),
            )
            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)],
                ["S", "O"],
            )

    def test_exact_trigger_alone_does_not_rename_a_persisted_id(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(root, [_entry("sample.save-v2", "S")])
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s"])

            self.assertEqual(store.snapshot(), {"SAMPLE.EXE": ["legacy:app:sample.exe:ctrl:s"]})
            self.assertEqual(
                store.effective_selected_ids_for("SAMPLE.EXE", catalog.entries),
                frozenset({"legacy:app:sample.exe:ctrl:s"}),
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

    def test_center_edit_preserves_stale_ids_and_existing_order(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(
                root,
                [_entry("sample.save", "S"), _entry("sample.new-recommended", "N", recommended=True)],
            )
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s", "retired:unknown"])
            model = ShortcutLibraryModel(catalog, store)

            model.set_checked("SAMPLE.EXE", "sample.new-recommended", True)

            self.assertEqual(
                store.selected_ids_in_order_for("SAMPLE.EXE"),
                ("legacy:app:sample.exe:ctrl:s", "retired:unknown", "sample.new-recommended"),
            )
            self.assertEqual(
                store.stale_selected_ids_for("SAMPLE.EXE", catalog.entries),
                ("retired:unknown",),
            )
            model.set_checked("SAMPLE.EXE", "legacy:app:sample.exe:ctrl:s", False)
            self.assertEqual(
                store.selected_ids_in_order_for("SAMPLE.EXE"),
                ("retired:unknown", "sample.new-recommended"),
            )

    def test_application_identity_alias_follows_existing_selection(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(
                root,
                [{**_entry("renamed.save", "S"), "id_aliases": ["legacy:app:sample.exe:ctrl:s"]}],
                app_identities=["RENAMED.EXE"],
                aliases=["SAMPLE.EXE"],
            )
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s"])

            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("RENAMED.EXE", "Ctrl", selection_store=store)],
                ["S"],
            )

    def test_pack_upgrade_preserves_legacy_user_only_and_hidden_builtin_layers(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = self._upgraded_catalog(
                root,
                [_entry("sample.save", "S", recommended=True), _entry("sample.new", "N", recommended=True)],
            )
            resolver = CatalogShortcutResolver(catalog)
            profiles = {
                "SAMPLE.EXE": {
                    "shortcuts": {"Ctrl": {"U": "User action"}},
                    "hidden_builtin": {"Ctrl": ["S"]},
                },
                "CUSTOM.EXE": {"shortcuts": {"Ctrl": {"K": "Custom action"}}},
            }

            self.assertEqual(
                [item.key for item in resolver.resolve("SAMPLE.EXE", "Ctrl", profiles)],
                ["U", "N"],
            )
            self.assertEqual(
                [item.key for item in resolver.resolve("CUSTOM.EXE", "Ctrl", profiles)],
                ["K"],
            )

    def test_non_pack_legacy_application_keeps_explicit_membership_and_order(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            _write_pack(root, [_entry("sample.save", "S")])
            legacy = ShortcutCatalog.from_legacy_shortcuts(
                {
                    "SAMPLE.EXE": {"Ctrl": {"S": "Save"}},
                    "LEGACY.EXE": {"Ctrl": {"L": "Legacy first", "O": "Legacy second"}},
                }
            )
            catalog = legacy.with_packs_from(root)
            store = self._store(
                root,
                ["legacy:app:legacy.exe:ctrl:o", "legacy:app:legacy.exe:ctrl:l"],
                "LEGACY.EXE",
            )

            self.assertEqual(
                [item.key for item in CatalogShortcutResolver(catalog).resolve("LEGACY.EXE", "Ctrl", selection_store=store)],
                ["O", "L"],
            )

    def test_catalog_reload_and_library_model_open_do_not_write_selection(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root, ["legacy:app:sample.exe:ctrl:s", "retired:unknown"])
            before = store.path.read_bytes()

            packs = root / "packs"
            packs.mkdir()
            catalog = self._upgraded_catalog(packs, [_entry("sample.save", "S")])
            CatalogShortcutResolver(catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=store)
            ShortcutLibraryModel(catalog, store).rows("SAMPLE.EXE")

            self.assertEqual(store.path.read_bytes(), before)

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

    def test_migration_is_deterministic_and_does_not_touch_real_user_paths(self) -> None:
        with TemporaryDirectory() as first, TemporaryDirectory() as second:
            first_root, second_root = Path(first), Path(second)
            first_catalog = self._upgraded_catalog(first_root, [_entry("sample.save-v2", "S")])
            second_catalog = self._upgraded_catalog(second_root, [_entry("sample.save-v2", "S")])
            first_store = self._store(first_root, ["legacy:app:sample.exe:ctrl:s"])
            second_store = self._store(second_root, ["legacy:app:sample.exe:ctrl:s"])

            self.assertEqual(
                first_store.effective_selected_ids_in_order_for("SAMPLE.EXE", first_catalog.entries),
                second_store.effective_selected_ids_in_order_for("SAMPLE.EXE", second_catalog.entries),
            )
            self.assertTrue(first_store.path.is_relative_to(first_root))
            self.assertTrue(second_store.path.is_relative_to(second_root))


if __name__ == "__main__":
    unittest.main()
