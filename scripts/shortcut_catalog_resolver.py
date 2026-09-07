"""Resolve Catalog entries into the legacy HUD presentation contract."""

from __future__ import annotations

from collections.abc import Mapping
from .modifier_state import normalize_modifier_combination
from .shortcut_catalog import CatalogEntry, CatalogScope, CatalogTrigger, ShortcutCatalog, select_catalog_text
from .shortcut_key import normalize_builtin_shortcut_identity
from .shortcut_resolver import (
    RESERVED_USER_IDENTITIES,
    ShortcutEntry,
    normalize_application_identity,
)

_GLOBAL_ONLY_IDENTITIES = frozenset(
    {"WINDOWS_SHELL", "SHELL_DESKTOP", "WPS_UNKNOWN"}
)


class CatalogShortcutResolver:
    """Compatibility resolver preserving existing HUD layer and key semantics."""

    def __init__(self, catalog: ShortcutCatalog) -> None:
        self._catalog = catalog

    def resolve(
        self,
        foreground_executable: str | None,
        modifier_combination: str | None,
        user_profiles: Mapping[str, object] | None = None,
        selection_store: object | None = None,
        language: str | None = None,
    ) -> list[ShortcutEntry]:
        canonical_modifier = normalize_modifier_combination(modifier_combination)
        if canonical_modifier is None:
            return []
        app_id = normalize_application_identity(foreground_executable)
        profile = _find_profile(user_profiles, app_id)
        app_entries = self._entries_for_app(app_id, canonical_modifier)
        app_is_known = self._has_application_entries(app_id)
        if profile is not None and not app_is_known and _profile_is_hidden_only(profile):
            profile = None
        layers: list[tuple[list[CatalogEntry], str]] = []
        if app_id not in _GLOBAL_ONLY_IDENTITIES:
            user_entries = _user_entries(profile, app_id, canonical_modifier)
            if profile is not None:
                layers.append((user_entries, "USER_APP"))
                if app_is_known:
                    layers.append((_hide_builtin(app_entries, profile, canonical_modifier), "APP"))
            elif app_is_known:
                layers.append((app_entries, "APP"))
            else:
                layers.append((self._entries_for_scope("DEFAULT", canonical_modifier), "DEFAULT"))
        layers.append((self._entries_for_scope("GLOBAL", canonical_modifier), "GLOBAL"))
        candidates = [
            (entry, source)
            for entries, source in layers
            for entry in entries
        ]
        selected = _selected_ids(selection_store, app_id, [entry for entry, _source in candidates])
        if selected is not None:
            candidates = [
                (entry, source)
                for entry, source in candidates
                if source == "GLOBAL" or entry.id in selected
            ]
        else:
            candidates = [
                (entry, source)
                for entry, source in candidates
                if source == "GLOBAL" or entry.recommended
            ]
        effective: list[tuple[CatalogEntry, str]] = []
        seen: set[str] = set()
        for entry, source in candidates:
            identity = entry.hud_key().casefold()
            if identity not in seen:
                seen.add(identity)
                effective.append((entry, source))
        return [
            ShortcutEntry(
                entry.hud_key(),
                _localized_description(entry.description, language),
                source,
            )
            for entry, source in effective
        ]

    def _entries_for_app(self, app_id: str | None, modifier: str) -> list[CatalogEntry]:
        if app_id is None:
            return []
        return sorted(
            [entry for entry in self._catalog.entries if entry.scope == "APP" and app_id in entry.application_ids and entry.matches_runtime_modifier(modifier) and "quick_hud" in entry.visibility],
            key=lambda entry: (entry.rank, entry.order),
        )

    def _has_application_entries(self, app_id: str | None) -> bool:
        return app_id is not None and any(
            entry.scope == "APP" and app_id in entry.application_ids
            for entry in self._catalog.entries
        )

    def _entries_for_scope(self, scope: CatalogScope, modifier: str) -> list[CatalogEntry]:
        return sorted(
            [entry for entry in self._catalog.entries if entry.scope == scope and entry.matches_runtime_modifier(modifier) and "quick_hud" in entry.visibility],
            key=lambda entry: (entry.rank, entry.order),
        )


def _find_profile(profiles: Mapping[str, object] | None, app_id: str | None) -> Mapping[str, object] | None:
    if not isinstance(profiles, Mapping) or app_id is None or app_id in RESERVED_USER_IDENTITIES:
        return None
    for candidate, profile in profiles.items():
        if isinstance(candidate, str) and isinstance(profile, Mapping) and normalize_application_identity(candidate) == app_id:
            return profile
    return None


def _user_entries(profile: Mapping[str, object] | None, app_id: str | None, modifier: str) -> list[CatalogEntry]:
    if profile is None or app_id is None or not isinstance(profile.get("shortcuts"), Mapping):
        return []
    entries: list[CatalogEntry] = []
    order = -100000
    for configured_modifier, keys in profile["shortcuts"].items():
        if not isinstance(configured_modifier, str) or normalize_modifier_combination(configured_modifier) != modifier or not isinstance(keys, Mapping):
            continue
        for key, description in keys.items():
            if not isinstance(key, str):
                continue
            entries.append(CatalogEntry(
                id=f"user:{app_id.casefold()}:{modifier.casefold()}:{key.casefold()}",
                trigger=CatalogTrigger("combo", tuple(modifier.split("+")) + (key,)),
                title={"en": key}, description=description, category="user", scope="APP", application_ids=(app_id,),
                recommended=True, rank=order, provenance={"kind": "user"}, visibility=frozenset({"quick_hud"}), builtin=False, aliases=(), order=order,
                legacy_runtime_modifier=modifier, legacy_display_key=key,
            ))
            order += 1
    return entries


def _hide_builtin(entries: list[CatalogEntry], profile: Mapping[str, object], modifier: str) -> list[CatalogEntry]:
    hidden = profile.get("hidden_builtin")
    if not isinstance(hidden, Mapping):
        return entries
    identities: set[str] = set()
    for configured_modifier, keys in hidden.items():
        if not isinstance(configured_modifier, str) or normalize_modifier_combination(configured_modifier) != modifier or not isinstance(keys, list):
            continue
        for key in keys:
            try:
                _modifier, normalized = normalize_builtin_shortcut_identity(modifier, key)
            except ValueError:
                continue
            identities.add(normalized.casefold())
    filtered: list[CatalogEntry] = []
    for entry in entries:
        try:
            _modifier, normalized = normalize_builtin_shortcut_identity(modifier, entry.hud_key())
        except ValueError:
            filtered.append(entry)
            continue
        if normalized.casefold() not in identities:
            filtered.append(entry)
    return filtered


def _profile_is_hidden_only(profile: Mapping[str, object]) -> bool:
    if isinstance(profile.get("display_name"), str) and profile["display_name"].strip():
        return False
    shortcuts = profile.get("shortcuts")
    if isinstance(shortcuts, Mapping) and any(isinstance(group, Mapping) and bool(group) for group in shortcuts.values()):
        return False
    hidden = profile.get("hidden_builtin")
    return isinstance(hidden, Mapping) and any(isinstance(group, list) and bool(group) for group in hidden.values())


def _selected_ids(
    store: object | None,
    app_id: str | None,
    entries: list[CatalogEntry],
) -> frozenset[str] | None:
    migration_method = getattr(store, "effective_selected_ids_for", None)
    if callable(migration_method):
        result = migration_method(app_id, entries)
        return frozenset(result) if result is not None else None
    method = getattr(store, "selected_ids_for", None)
    if not callable(method):
        return None
    result = method(app_id)
    return frozenset(result) if result is not None else None


def _localized_description(value: object, language: str | None) -> object:
    """Resolve Catalog text once, before any presentation consumes it."""

    if language is None or not isinstance(value, Mapping):
        return value
    return select_catalog_text(value, language)
