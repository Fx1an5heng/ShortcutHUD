"""Conservative presentation-only equivalence; never changes IDs or selections."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import json

from .shortcut_catalog import CatalogEntry
from .shortcut_key import normalize_builtin_shortcut_identity, normalize_shortcut_key


def normalized_trigger(entry: CatalogEntry) -> tuple[str, ...]:
    if entry.trigger.kind == "combo":
        try:
            modifier, key = normalize_builtin_shortcut_identity(
                entry.legacy_runtime_modifier or entry.trigger.runtime_modifier(), entry.hud_key())
            return ("combo", modifier, key.casefold())
        except ValueError:
            pass
    strokes = []
    for stroke in entry.trigger.keys:
        try:
            if "+" in stroke and entry.trigger.kind == "sequence":
                modifier, key = normalize_builtin_shortcut_identity(*stroke.rsplit("+", 1))
                strokes.append(f"{modifier}+{key}".casefold())
            else:
                strokes.append(normalize_shortcut_key(stroke).casefold())
        except ValueError:
            strokes.append(stroke.casefold())
    return (entry.trigger.kind, *strokes)


def _english(value: object) -> str:
    value = value.get("en", "") if isinstance(value, Mapping) else value
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


def _priority(entry: CatalogEntry):
    provenance = entry.provenance
    kind = provenance.get("kind")
    origin = 2 if kind == "legacy" else 1 if kind == "imported" or provenance.get("upstream_package") else 0
    return (origin, entry.rank, entry.order, entry.id)


def _equivalent(left: CatalogEntry, right: CatalogEntry) -> bool:
    left_tokens = {left.id, *left.id_aliases}
    right_tokens = {right.id, *right.id_aliases}
    for entry, tokens in ((left, left_tokens), (right, right_tokens)):
        semantic = entry.provenance.get("presentation_semantic_id")
        if isinstance(semantic, str) and semantic:
            tokens.add(semantic)
    if left_tokens & right_tokens:
        return True
    # Reviewed legacy labels are constrained by app + complete trigger below.
    # Unknown/changed labels remain visible; this is NOT a selection alias.
    for legacy, formal in ((left, right), (right, left)):
        labels = formal.provenance.get("presentation_legacy_titles", ())
        if legacy.provenance.get("kind") == "legacy" and isinstance(labels, (list, tuple)):
            if _english(legacy.title) in {_english(label) for label in labels if isinstance(label, str)}:
                return True
    # Conflicting explicit semantic IDs must not be collapsed by equal text.
    if left.provenance.get("presentation_semantic_id") or right.provenance.get("presentation_semantic_id"):
        return False
    title, description = _english(left.title), _english(left.description)
    return bool(title and description
                and title == _english(right.title) and description == _english(right.description))


def presentation_groups(entries: list[CatalogEntry], app_id: str | None):
    """Return (preferred entry, all equivalent records), deterministically.

    Application scope, every stroke and explicit context are hard boundaries.
    Equivalence needs stable alias, reviewed semantic metadata or an exact
    English title+description fingerprint, never fuzzy translation. Category
    is intentionally not identity: equivalent native/imported rows may have
    been filed under different headings.
    """
    buckets = defaultdict(list)
    for entry in entries:
        scope = (app_id,) if app_id in entry.application_ids else tuple(sorted(entry.application_ids))
        context = json.dumps(entry.provenance.get("context"), sort_keys=True, ensure_ascii=False)
        buckets[(entry.scope, scope, normalized_trigger(entry), context)].append(entry)
    groups = []
    for bucket in buckets.values():
        components: list[list[CatalogEntry]] = []
        for entry in sorted(bucket, key=_priority):
            matching = [group for group in components if any(_equivalent(entry, member) for member in group)]
            merged = [entry]
            for group in matching:
                merged.extend(group)
                components.remove(group)
            components.append(merged)
        for component in components:
            members = tuple(sorted(component, key=_priority))
            groups.append((members[0], members))
    return sorted(groups, key=lambda group: (group[0].rank, group[0].order, group[0].id))
