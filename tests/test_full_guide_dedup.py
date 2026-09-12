"""Presentation equivalence is separate from trigger conflict and selection."""
from dataclasses import replace
import unittest

from scripts.catalog_presentation_dedup import presentation_groups
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import resolve_catalog_view
from tests.test_full_guide_data import entry


class GuideDedupTests(unittest.TestCase):
    def resolved(self, entries, profiles=None):
        return resolve_catalog_view(ShortcutCatalog(entries), "SAMPLE.EXE", profiles, "zh_CN")

    def test_exact_duplicate_has_one_presentation_record(self):
        original = entry("native")
        duplicate = replace(original, id="imported", category="other-section")
        rows = self.resolved([original, duplicate])
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(presentation_groups([original, duplicate], "SAMPLE.EXE")[0][1]), 2)

    def test_declared_equivalence_prefers_native_and_keeps_search_synonyms(self):
        native = replace(entry("native"), rank=50)
        imported = replace(entry("imported", description={"en": "Persist buffer", "zh_CN": "保存缓冲区"}), rank=1,
                           provenance={"kind": "imported", "presentation_semantic_id": "native"})
        rows = self.resolved([imported, native])
        self.assertEqual([row.entry.id for row in rows], ["native"])
        self.assertIn("persist buffer", rows[0].search_text)

    def test_declared_stable_alias_can_merge(self):
        native = replace(entry("native"), id_aliases=("old",))
        self.assertEqual(len(self.resolved([native, entry("old")])), 1)

    def test_same_trigger_different_semantics_survives(self):
        self.assertEqual(len(self.resolved([entry("save"), entry("chat", description={"en": "Open chat"})])), 2)

    def test_explicit_different_context_never_merges_even_same_semantic(self):
        first = replace(entry("a"), provenance={"presentation_semantic_id": "shared", "context": "editor"})
        second = replace(first, id="b", provenance={"presentation_semantic_id": "shared", "context": "debugger"})
        self.assertEqual(len(self.resolved([first, second])), 2)

    def test_explicit_semantics_override_equal_labels(self):
        first = replace(entry("a"), provenance={"presentation_semantic_id": "save"})
        second = replace(first, id="b", provenance={"presentation_semantic_id": "chat"})
        self.assertEqual(len(self.resolved([first, second])), 2)

    def test_different_apps_never_merge(self):
        first = entry("same")
        second = replace(first, application_ids=("OTHER.EXE",))
        self.assertEqual(len(presentation_groups([first, second], "SAMPLE.EXE")), 2)

    def test_dedup_is_deterministic_independent_of_candidate_iteration(self):
        first = entry("native")
        second = replace(entry("upstream"), provenance={"kind": "imported", "presentation_semantic_id": "native"})
        self.assertEqual(self.resolved([first, second]), self.resolved([second, first]))

    def test_single_key_duplicate_normalizes_case(self):
        first = entry("run", ("F5",), kind="single")
        second = replace(first, id="old-run", trigger=replace(first.trigger, keys=("f5",)), id_aliases=("run",))
        self.assertEqual(len(self.resolved([first, second])), 1)

    def test_sequence_duplicate_compares_all_strokes(self):
        first = entry("keys", ("Ctrl+K", "Ctrl+S"), kind="sequence")
        second = replace(first, id="old-keys", trigger=replace(first.trigger, keys=("ctrl+k", "CTRL+s")), id_aliases=("keys",))
        third = replace(second, id="different", trigger=replace(first.trigger, keys=("Ctrl+J", "Ctrl+S")))
        self.assertEqual(len(self.resolved([first, second, third])), 2)

    def test_user_overrides_all_equivalent_builtin_and_global(self):
        native = entry("native")
        imported = replace(native, id="imported")
        global_entry = entry("global", scope="GLOBAL")
        rows = self.resolved([native, imported, global_entry], {"SAMPLE.EXE": {"shortcuts": {"Ctrl": {"S": "Personal action"}}}})
        self.assertEqual([(row.source, row.description) for row in rows], [("USER_APP", "Personal action")])

    def test_unknown_legacy_semantics_not_discarded_by_same_trigger(self):
        catalog = ShortcutCatalog.from_legacy_shortcuts({"SAMPLE.EXE": {"Ctrl": {"S": "Other action"}}})
        catalog.entries += (entry(),)
        self.assertEqual(len(resolve_catalog_view(catalog, "SAMPLE.EXE")), 2)

    def test_original_catalog_and_aliases_never_mutated(self):
        original = entry("native")
        duplicate = replace(original, id="duplicate")
        catalog = ShortcutCatalog([original, duplicate])
        before = repr(catalog.entries)
        resolve_catalog_view(catalog, "SAMPLE.EXE")
        self.assertEqual(repr(catalog.entries), before)
