"""Full Guide Pin mutates one semantic selection and preserves every other ID."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.full_guide_pin import FullGuidePinService
from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver
from tests.test_full_guide_data import entry


def quick(identifier, keys, recommended=False, aliases=()):
    return replace(entry(identifier, keys, recommended=recommended), visibility=frozenset({"quick_hud", "full_guide"}), id_aliases=aliases)


class FullGuidePinTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "selection.json"
        self.store = QuickHudSelectionStore(self.path)
        self.save = quick("save", ("Ctrl", "S"), True, ("old-save",))
        self.open = quick("open", ("Ctrl", "O"))
        self.alt = quick("alt", ("Alt", "A"), True)
        self.sequence = replace(entry("sequence", ("Ctrl+K", "Ctrl+S"), kind="sequence"), visibility=frozenset({"full_guide"}))
        self.catalog = ShortcutCatalog((self.save, self.open, self.alt, self.sequence))
        self.service = FullGuidePinService(self.catalog, self.store, "SAMPLE.EXE")

    def test_explicit_pin_appends_only_target_and_preserves_stale_order(self):
        self.store.set_selected_ids("SAMPLE.EXE", ["stale", "save", "unknown"])
        self.store.save()
        other_before = ["stale", "save", "unknown"]
        self.assertTrue(self.service.set_pinned("open", True))
        self.assertEqual(self.store.selected_ids_in_order_for("SAMPLE.EXE"), (*other_before, "open"))
        reloaded = QuickHudSelectionStore(self.path)
        reloaded.load()
        self.assertEqual(reloaded.selected_ids_in_order_for("SAMPLE.EXE"), (*other_before, "open"))

    def test_unpin_removes_only_target_identity_including_declared_alias(self):
        self.store.set_selected_ids("SAMPLE.EXE", ["stale", "old-save", "open"])
        self.assertTrue(self.service.set_pinned("save", False))
        self.assertEqual(self.store.selected_ids_in_order_for("SAMPLE.EXE"), ("stale", "open"))

    def test_never_configured_pin_materializes_recommended_then_target(self):
        self.assertTrue(self.service.set_pinned("open", True))
        self.assertEqual(self.store.selected_ids_in_order_for("SAMPLE.EXE"), ("save", "alt", "open"))

    def test_never_configured_unpin_recommended_materializes_minus_target(self):
        self.assertTrue(self.service.is_pinned(self.save))
        self.assertTrue(self.service.set_pinned("save", False))
        self.assertEqual(self.store.selected_ids_in_order_for("SAMPLE.EXE"), ("alt",))

    def test_explicit_empty_stays_explicit_and_pin_adds_only_target(self):
        self.store.set_selected_ids("SAMPLE.EXE", [])
        self.assertFalse(self.service.is_pinned(self.save))
        self.assertTrue(self.service.set_pinned("open", True))
        self.assertEqual(self.store.selected_ids_in_order_for("SAMPLE.EXE"), ("open",))

    def test_catalog_only_sequence_cannot_pin(self):
        self.assertNotIn("sequence", self.service.pin_states())
        self.assertFalse(self.service.set_pinned("sequence", True))
        self.assertIsNone(self.store.selected_ids_for("SAMPLE.EXE"))

    def test_quick_hud_reads_pin_on_next_resolution(self):
        self.store.set_selected_ids("SAMPLE.EXE", [])
        self.service.set_pinned("open", True)
        rows = CatalogShortcutResolver(self.catalog).resolve("SAMPLE.EXE", "Ctrl", selection_store=self.store)
        self.assertEqual([row.key for row in rows], ["O"])

    def test_other_application_and_unknown_ids_survive_save(self):
        self.store.set_selected_ids("OTHER.EXE", ["other-stale"])
        self.store.set_selected_ids("SAMPLE.EXE", ["sample-stale"])
        self.service.set_pinned("open", True)
        self.assertEqual(self.store.snapshot()["OTHER.EXE"], ["other-stale"])
        self.assertEqual(self.store.snapshot()["SAMPLE.EXE"], ["sample-stale", "open"])

    def test_failed_save_rolls_back_in_memory_selection(self):
        self.store.set_selected_ids("SAMPLE.EXE", ["stale", "save"])
        previous = self.store.snapshot()
        original_save = self.store.save

        def fail_save():
            raise OSError("simulated write failure")

        self.store.save = fail_save
        try:
            with self.assertRaisesRegex(OSError, "simulated write failure"):
                self.service.set_pinned("open", True)
        finally:
            self.store.save = original_save
        self.assertEqual(self.store.snapshot(), previous)


if __name__ == "__main__":
    unittest.main()
