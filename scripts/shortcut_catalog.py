"""Catalog domain model and compatibility bridge for ShortcutHUD shortcuts.

The legacy ``shortcuts.json`` remains the shipping data source during the
Catalog foundation phase.  This module gives that data stable identities and a
pack-shaped API without changing the HUD's visible behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlparse

from .modifier_state import canonicalize_modifier_state, normalize_modifier_combination, normalize_modifier_token
from .shortcut_resolver import normalize_application_identity


CatalogScope = Literal["APP", "DEFAULT", "GLOBAL"]
TriggerKind = Literal["single", "combo", "sequence", "double_tap"]
PACK_SCHEMA_VERSION = 1
_ENTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
_VALID_VISIBILITY = frozenset({"quick_hud", "full_guide"})
logger = logging.getLogger(__name__)


class CatalogValidationError(ValueError):
    """A pack cannot safely enter the in-memory catalog."""


@dataclass(frozen=True, slots=True)
class CatalogLoadIssue:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class CatalogTrigger:
    kind: TriggerKind
    keys: tuple[str, ...]

    def runtime_modifier(self) -> str | None:
        """Return the modifier state understood by the current Quick HUD."""

        if self.kind != "combo" or len(self.keys) < 2:
            return None
        return canonicalize_modifier_state(self.keys[:-1])

    def is_quick_hud_eligible(self) -> bool:
        return self.kind == "combo" and self.runtime_modifier() is not None

    def display_key(self) -> str:
        return self.keys[-1] if self.kind == "combo" else " ".join(self.keys)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    id: str
    trigger: CatalogTrigger
    title: Mapping[str, str]
    description: object
    category: str
    scope: CatalogScope
    application_ids: tuple[str, ...]
    recommended: bool
    rank: int
    provenance: Mapping[str, object]
    visibility: frozenset[str]
    builtin: bool
    aliases: tuple[str, ...]
    order: int
    legacy_runtime_modifier: str | None = None
    legacy_display_key: str | None = None
    id_aliases: tuple[str, ...] = ()

    def matches_runtime_modifier(self, modifier: str) -> bool:
        return (self.legacy_runtime_modifier or self.trigger.runtime_modifier()) == modifier

    def hud_key(self) -> str:
        return self.legacy_display_key or self.trigger.display_key()


@dataclass(frozen=True, slots=True)
class ShortcutPack:
    id: str
    product: Mapping[str, str]
    application_ids: tuple[str, ...]
    aliases: tuple[str, ...]
    platforms: tuple[str, ...]
    locales: tuple[str, ...]
    source: Mapping[str, object]
    coverage: Mapping[str, object]
    categories: Mapping[str, Mapping[str, str]]
    entries: tuple[CatalogEntry, ...]


class ShortcutCatalog:
    """Immutable-ish ordered catalog; invalid external packs fail closed."""

    def __init__(self, entries: Iterable[CatalogEntry] = ()) -> None:
        self.entries = tuple(entries)
        self.load_issues: list[CatalogLoadIssue] = []
        self.application_titles: dict[str, Mapping[str, str]] = {}
        self.application_product_ids: dict[str, str] = {}
        self.category_titles: dict[str, Mapping[str, str]] = {}

    @classmethod
    def from_legacy_shortcuts(cls, shortcut_data: Mapping[str, object]) -> "ShortcutCatalog":
        """Adapt legacy mapping data with deterministic, stable entry IDs."""

        entries: list[CatalogEntry] = []
        if not isinstance(shortcut_data, Mapping):
            return cls()
        order = 0
        for raw_app_id, raw_layer in shortcut_data.items():
            if not isinstance(raw_app_id, str) or not isinstance(raw_layer, Mapping):
                continue
            app_id = normalize_application_identity(raw_app_id)
            if app_id is None:
                continue
            scope: CatalogScope = (
                "DEFAULT" if app_id == "DEFAULT" else "GLOBAL" if app_id == "GLOBAL" else "APP"
            )
            application_ids = () if scope != "APP" else (app_id,)
            for raw_modifier, raw_shortcuts in raw_layer.items():
                if not isinstance(raw_modifier, str) or not isinstance(raw_shortcuts, Mapping):
                    continue
                runtime_modifier = _legacy_runtime_modifier(raw_modifier)
                if runtime_modifier is None:
                    continue
                for raw_key, description in raw_shortcuts.items():
                    if not isinstance(raw_key, str):
                        continue
                    display_key = raw_key if normalize_modifier_combination(raw_modifier) else (
                        raw_modifier if not raw_key else f"{raw_modifier} {raw_key}"
                    )
                    entry_id = _legacy_entry_id(scope, app_id, raw_modifier, raw_key)
                    entries.append(
                        CatalogEntry(
                            id=entry_id,
                            trigger=CatalogTrigger("combo", tuple(runtime_modifier.split("+")) + (display_key,)),
                            title=_legacy_localized_text(description),
                            description=description,
                            category="legacy",
                            scope=scope,
                            application_ids=application_ids,
                            recommended=True,
                            rank=order,
                            provenance={"kind": "legacy", "source": "config/shortcuts.json"},
                            visibility=frozenset({"quick_hud"}),
                            builtin=True,
                            aliases=(),
                            order=order,
                            legacy_runtime_modifier=runtime_modifier,
                            legacy_display_key=display_key,
                        )
                    )
                    order += 1
        return cls(entries)

    @classmethod
    def load_packs(cls, directory: str | Path) -> "ShortcutCatalog":
        """Load valid JSON packs in path order; report and skip invalid files."""

        catalog = cls()
        path = Path(directory)
        if not path.exists():
            return catalog
        entries: list[CatalogEntry] = []
        seen_ids: set[str] = set()
        seen_pack_ids: set[str] = set()
        for pack_path in sorted(path.glob("*.json"), key=lambda item: item.name.casefold()):
            try:
                document = json.loads(pack_path.read_text(encoding="utf-8"))
                pack = parse_shortcut_pack(document, base_order=len(entries))
                if pack.id in seen_pack_ids:
                    raise CatalogValidationError(f"duplicate pack id: {pack.id}")
                for entry in pack.entries:
                    if entry.id in seen_ids:
                        raise CatalogValidationError(f"duplicate catalog entry id: {entry.id}")
                seen_pack_ids.add(pack.id)
                seen_ids.update(entry.id for entry in pack.entries)
                entries.extend(pack.entries)
                for app_id in (*pack.application_ids, *pack.aliases):
                    catalog.application_titles[app_id] = pack.product
                    catalog.application_product_ids[app_id] = pack.id
                catalog.category_titles.update(pack.categories)
            except (OSError, UnicodeError, json.JSONDecodeError, CatalogValidationError) as error:
                catalog.load_issues.append(CatalogLoadIssue(pack_path, str(error)))
                logger.warning("Ignoring invalid shortcut pack %s: %s", pack_path, error)
        catalog.entries = tuple(entries)
        return catalog

    def with_packs_from(self, directory: str | Path) -> "ShortcutCatalog":
        """Append valid optional packs while preserving legacy order and IDs."""

        external = self.load_packs(directory)
        known_ids = {entry.id for entry in self.entries}
        formal_applications = {
            app_id
            for entry in external.entries
            if entry.scope == "APP" and entry.builtin
            for app_id in entry.application_ids
        }
        appended: list[CatalogEntry] = [
            entry for entry in self.entries
            if not (
                entry.id.startswith("legacy:app:")
                and any(app_id in formal_applications for app_id in entry.application_ids)
            )
        ]
        issues = list(external.load_issues)
        for entry in external.entries:
            if entry.id in known_ids:
                issues.append(CatalogLoadIssue(Path(directory), f"duplicate catalog entry id: {entry.id}"))
                logger.warning("Ignoring duplicate shortcut catalog entry: %s", entry.id)
                continue
            known_ids.add(entry.id)
            appended.append(entry)
        result = ShortcutCatalog(appended)
        result.load_issues = issues
        result.application_titles = dict(self.application_titles)
        result.application_titles.update(external.application_titles)
        result.application_product_ids = dict(self.application_product_ids)
        result.application_product_ids.update(external.application_product_ids)
        result.category_titles = dict(self.category_titles)
        result.category_titles.update(external.category_titles)
        return result


def select_catalog_text(value: Mapping[str, str], language: str | None) -> str:
    """Choose a localized Catalog field with stable, language-aware fallback."""

    if not value:
        return ""
    requested = language.casefold().replace("-", "_") if isinstance(language, str) else ""
    candidates = (requested, requested.split("_", 1)[0])
    normalized = {key.casefold().replace("-", "_"): text for key, text in value.items()}
    for candidate in candidates:
        text = normalized.get(candidate)
        if text is not None:
            return text
    if requested:
        base_language = requested.split("_", 1)[0]
        for candidate, text in normalized.items():
            if candidate.startswith(f"{base_language}_"):
                return text
    for candidate in ("en", "zh_CN", "zh"):
        text = normalized.get(candidate.casefold())
        if text is not None:
            return text
    return next(iter(value.values()))


def parse_shortcut_pack(document: object, *, base_order: int = 0) -> ShortcutPack:
    if not isinstance(document, Mapping):
        raise CatalogValidationError("pack root must be an object")
    if document.get("schema_version") != PACK_SCHEMA_VERSION:
        raise CatalogValidationError("unsupported pack schema_version")
    pack_id = _required_id(document.get("id"), "pack id")
    product = _localized_mapping(document.get("product"), "product")
    application_ids = _application_ids(document.get("app_identities"), "app_identities")
    aliases = _application_ids(document.get("aliases", ()), "aliases")
    if set(application_ids) & set(aliases):
        raise CatalogValidationError("aliases duplicate app_identities")
    platforms = _string_list(document.get("platforms", ("windows",)), "platforms")
    locales = _string_list(document.get("locales", ()), "locales")
    source = _source_mapping(document.get("source"), "source")
    coverage = _coverage_mapping(document.get("coverage"))
    categories = _category_mapping(document.get("categories", {}))
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise CatalogValidationError("entries must be an array")
    entry_application_ids = tuple(dict.fromkeys((*application_ids, *aliases)))
    entries: list[CatalogEntry] = []
    local_ids: set[str] = set()
    for index, raw_entry in enumerate(raw_entries):
        entry = _parse_entry(raw_entry, entry_application_ids, base_order + index)
        if categories and entry.category not in categories:
            raise CatalogValidationError(f"entry category is not declared: {entry.category}")
        if entry.id in local_ids:
            raise CatalogValidationError(f"duplicate entry id in pack: {entry.id}")
        local_ids.add(entry.id)
        entries.append(entry)
    return ShortcutPack(pack_id, product, application_ids, aliases, platforms, locales, source, coverage, categories, tuple(entries))


def _parse_entry(raw: object, pack_apps: tuple[str, ...], order: int) -> CatalogEntry:
    if not isinstance(raw, Mapping):
        raise CatalogValidationError("entry must be an object")
    entry_id = _required_id(raw.get("id"), "entry id")
    trigger = _parse_trigger(raw.get("trigger"))
    scope = raw.get("scope", "app")
    normalized_scope = {"app": "APP", "default": "DEFAULT", "global": "GLOBAL"}.get(scope)
    if normalized_scope is None:
        raise CatalogValidationError("entry scope must be app, default, or global")
    application_ids = pack_apps if normalized_scope == "APP" else ()
    if normalized_scope == "APP" and not application_ids:
        raise CatalogValidationError("app entry requires app_identities")
    recommended = raw.get("recommended", False)
    rank = raw.get("rank", 0)
    builtin = raw.get("builtin", True)
    if not isinstance(recommended, bool) or not isinstance(builtin, bool) or not isinstance(rank, int):
        raise CatalogValidationError("recommended, builtin, and rank have invalid types")
    visibility = frozenset(_string_list(raw.get("visibility", ("quick_hud",)), "visibility"))
    if not visibility <= _VALID_VISIBILITY:
        raise CatalogValidationError("entry visibility is invalid")
    return CatalogEntry(
        id=entry_id,
        trigger=trigger,
        title=_localized_mapping(raw.get("title"), "entry title"),
        description=_localized_mapping(raw.get("description"), "entry description"),
        category=_required_text(raw.get("category"), "category"),
        scope=normalized_scope,
        application_ids=application_ids,
        recommended=recommended,
        rank=rank,
        provenance=_source_mapping(raw.get("provenance"), "provenance"),
        visibility=visibility,
        builtin=builtin,
        aliases=_string_list(raw.get("aliases", ()), "entry aliases"),
        order=order,
        id_aliases=_id_list(raw.get("id_aliases", ()), "entry id_aliases"),
    )


def _parse_trigger(raw: object) -> CatalogTrigger:
    if not isinstance(raw, Mapping):
        raise CatalogValidationError("trigger must be an object")
    kind = raw.get("kind")
    if kind not in {"single", "combo", "sequence", "double_tap"}:
        raise CatalogValidationError("trigger kind is invalid")
    keys = _string_list(raw.get("keys"), "trigger keys")
    if not keys:
        raise CatalogValidationError("trigger keys must not be empty")
    if kind == "combo" and len(keys) < 2:
        raise CatalogValidationError("combo trigger requires modifier and terminal key")
    if kind == "single" and len(keys) != 1:
        raise CatalogValidationError("single trigger requires exactly one key")
    return CatalogTrigger(kind, keys)


def _legacy_runtime_modifier(configured_modifier: str) -> str | None:
    canonical = normalize_modifier_combination(configured_modifier)
    if canonical is not None:
        return canonical
    first_stroke = configured_modifier.split(" ", 1)[0]
    tokens = first_stroke.split("+")
    modifiers = [token for token in tokens if normalize_modifier_token(token) is not None]
    non_modifiers = [token for token in tokens if normalize_modifier_token(token) is None]
    return canonicalize_modifier_state(modifiers) if modifiers and non_modifiers else None


def _legacy_entry_id(scope: str, app_id: str, modifier: str, key: str) -> str:
    escaped = ":".join(part.replace(":", "%3a") for part in (scope.casefold(), app_id.casefold(), modifier.casefold(), key.casefold()))
    return f"legacy:{escaped}"


def _legacy_localized_text(description: object) -> Mapping[str, str]:
    if isinstance(description, Mapping):
        result = {str(key): value for key, value in description.items() if isinstance(key, str) and isinstance(value, str)}
        if result:
            if "zh" in result and "zh_CN" not in result:
                result["zh_CN"] = result["zh"]
            return result
    return {"en": description} if isinstance(description, str) else {"en": ""}


def _required_id(value: object, name: str) -> str:
    result = _required_text(value, name)
    if not _ENTRY_ID_PATTERN.fullmatch(result):
        raise CatalogValidationError(f"{name} is not a stable id")
    return result


def _id_list(value: object, name: str) -> tuple[str, ...]:
    values = _string_list(value, name)
    if any(
        not _ENTRY_ID_PATTERN.fullmatch(item) and not item.startswith("legacy:")
        for item in values
    ):
        raise CatalogValidationError(f"{name} contains an invalid stable id")
    return values


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogValidationError(f"{name} must be a non-empty string")
    return value.strip()


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise CatalogValidationError(f"{name} must be an array")
    result = tuple(_required_text(item, name) for item in value)
    if len({item.casefold() for item in result}) != len(result):
        raise CatalogValidationError(f"{name} contains duplicates")
    return result


def _application_ids(value: object, name: str) -> tuple[str, ...]:
    result = _string_list(value, name)
    normalized = tuple(normalize_application_identity(item) for item in result)
    if any(item is None for item in normalized) or len(set(normalized)) != len(normalized):
        raise CatalogValidationError(f"{name} contains invalid or duplicate identities")
    return tuple(item for item in normalized if item is not None)


def _localized_mapping(value: object, name: str) -> Mapping[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise CatalogValidationError(f"{name} must be a non-empty localized object")
    result: dict[str, str] = {}
    for language, text in value.items():
        if not isinstance(language, str) or not language.strip() or not isinstance(text, str) or not text.strip():
            raise CatalogValidationError(f"{name} contains invalid localized text")
        result[language] = text
    return result


def _category_mapping(value: object) -> Mapping[str, Mapping[str, str]]:
    if not isinstance(value, Mapping):
        raise CatalogValidationError("categories must be an object")
    result: dict[str, Mapping[str, str]] = {}
    for category, labels in value.items():
        if not isinstance(category, str) or not _ENTRY_ID_PATTERN.fullmatch(category):
            raise CatalogValidationError("category key is not a stable id")
        result[category] = _localized_mapping(labels, "category label")
    return result


def _source_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CatalogValidationError(f"{name} must be an object")
    title = _required_text(value.get("title"), f"{name} title")
    url = _required_text(value.get("url"), f"{name} url")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CatalogValidationError(f"{name} url must be an http(s) URL")
    return {**value, "title": title, "url": url}


def _coverage_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CatalogValidationError("coverage must be an object")
    status = value.get("status")
    if status not in {"partial", "substantial", "verified_complete"}:
        raise CatalogValidationError("coverage status is invalid")
    title = _required_text(value.get("official_reference_title"), "coverage official_reference_title")
    url = _source_mapping({"title": title, "url": value.get("official_reference_url")}, "coverage")["url"]
    date = _required_text(value.get("verified_date"), "coverage verified_date")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise CatalogValidationError("coverage verified_date must use YYYY-MM-DD")
    return {"status": status, "official_reference_title": title, "official_reference_url": url, "verified_date": date}
