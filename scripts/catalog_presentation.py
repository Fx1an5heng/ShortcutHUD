"""Shared localized Catalog presentation values; no UI or persistence."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .shortcut_catalog import CatalogEntry, ShortcutCatalog, select_catalog_text


def localized_description(value: object, language: str | None) -> str:
    if isinstance(value, Mapping):
        return select_catalog_text({key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, str)}, language)
    return value if isinstance(value, str) else ""


def description_values(value: object) -> tuple[str, ...]:
    return tuple(item for item in value.values() if isinstance(item, str)) if isinstance(value, Mapping) else (value,) if isinstance(value, str) else ()


def trigger_text(entry: CatalogEntry) -> str:
    if entry.trigger.kind == "double_tap":
        return f'{" ".join(entry.trigger.keys)} × 2'
    return "+".join(entry.trigger.keys) if entry.trigger.kind == "combo" else " ".join(entry.trigger.keys)


def category_label(catalog: ShortcutCatalog, category: str, language: str | None) -> str:
    chinese = isinstance(language, str) and language.casefold().startswith("zh")
    special = {"legacy": ("其他", "Other"), "user": ("我的快捷键", "My Shortcuts"), "global": ("全局", "Global")}
    if category in special:
        return special[category][0 if chinese else 1]
    labels = catalog.category_titles.get(category)
    return select_catalog_text(labels, language) if labels else category


@dataclass(frozen=True, slots=True)
class ResolvedCatalogEntry:
    entry: CatalogEntry
    source: str
    trigger: str
    title: str
    description: str
    category: str
    category_title: str
    search_text: str


def resolve_presentation(catalog: ShortcutCatalog, entry: CatalogEntry, source: str, language: str | None) -> ResolvedCatalogEntry:
    title = select_catalog_text(entry.title, language)
    description = localized_description(entry.description, language)
    category = "global" if source == "GLOBAL" else entry.category
    label = category_label(catalog, category, language)
    trigger = trigger_text(entry)
    terms = (trigger, title, description, label, category, *entry.title.values(), *description_values(entry.description), *entry.aliases, *catalog.category_titles.get(entry.category, {}).values())
    return ResolvedCatalogEntry(entry, source, trigger, title, description, category, label, "\n".join(terms).casefold())
