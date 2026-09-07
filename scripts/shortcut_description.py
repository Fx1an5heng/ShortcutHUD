"""Language-aware selection for bilingual shortcut descriptions."""

from __future__ import annotations

from collections.abc import Mapping

from .shortcut_catalog import select_catalog_text


def select_description_text(description: object, language: str | None) -> str:
    """Return display text without changing resolver-owned description data."""

    if isinstance(description, str):
        return description
    if not isinstance(description, Mapping):
        return "N/A"

    text = select_catalog_text(description, language)
    return text or "N/A"
