"""Safe one-entry Quick HUD selection mutations initiated by Full Guide."""
from __future__ import annotations

from .shortcut_resolver import normalize_application_identity


class FullGuidePinService:
    def __init__(self, catalog, selection_store, app_id: str | None) -> None:
        self.catalog = catalog
        self.store = selection_store
        self.app_id = normalize_application_identity(app_id)
        self.entries = tuple(
            entry for entry in catalog.entries
            if self.app_id is not None
            and entry.scope == "APP"
            and any(normalize_application_identity(candidate) == self.app_id for candidate in entry.application_ids)
        )
        self._eligible = {entry.id: entry for entry in self.entries if self.is_eligible(entry)}

    @staticmethod
    def is_eligible(entry) -> bool:
        return bool(entry.scope == "APP" and entry.trigger.is_quick_hud_eligible() and "quick_hud" in entry.visibility)

    def pin_states(self) -> dict[str, bool]:
        return {entry_id: self.is_pinned(entry) for entry_id, entry in self._eligible.items()}

    def is_pinned(self, entry) -> bool:
        if not self.is_eligible(entry):
            return False
        _identity, selected = self._stored_selection()
        if selected is None:
            return bool(entry.recommended)
        identities = {entry.id, *entry.id_aliases}
        return any(identifier in identities for identifier in selected)

    def set_pinned(self, entry_id: str, pinned: bool) -> bool:
        if self.store is None or self.app_id is None or entry_id not in self._eligible:
            return False
        target = self._eligible[entry_id]
        storage_identity, previous = self._stored_selection()
        selected = list(self._recommended_ids() if previous is None else previous)
        target_identities = {target.id, *target.id_aliases}
        currently_pinned = any(identifier in target_identities for identifier in selected)
        if pinned == currently_pinned:
            return False
        if pinned:
            selected.append(target.id)
        else:
            selected = [identifier for identifier in selected if identifier not in target_identities]

        write_identity = storage_identity or self.app_id
        self.store.set_selected_ids(write_identity, selected)
        try:
            self.store.save()
        except Exception:
            if previous is None:
                self.store.clear_selection(write_identity)
            else:
                self.store.set_selected_ids(write_identity, previous)
            raise
        return True

    def _stored_selection(self) -> tuple[str | None, tuple[str, ...] | None]:
        if self.store is None or self.app_id is None:
            return None, None
        snapshot = self.store.snapshot()
        if self.app_id in snapshot:
            return self.app_id, tuple(snapshot[self.app_id])
        for entry in self.entries:
            for candidate in entry.application_ids:
                identity = normalize_application_identity(candidate)
                if identity in snapshot:
                    return identity, tuple(snapshot[identity])
        return None, None

    def _recommended_ids(self) -> tuple[str, ...]:
        selected = []
        seen_keys = set()
        for entry in sorted(self._eligible.values(), key=lambda item: (item.rank, item.order)):
            key = entry.hud_key().casefold()
            if entry.recommended and key not in seen_keys:
                selected.append(entry.id)
                seen_keys.add(key)
        return tuple(selected)
