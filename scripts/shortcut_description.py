"""Language-aware selection for bilingual shortcut descriptions."""

from __future__ import annotations

from collections.abc import Mapping


def select_description_text(description: object, language: str | None) -> str:
    """Return display text without changing resolver-owned description data."""

    if isinstance(description, str):
        return description
    if not isinstance(description, Mapping):
        return "N/A"

    language_code = (
        language.split("_", 1)[0].casefold()
        if isinstance(language, str) and language
        else "en"
    )
    fallback_codes = [language_code]
    if language_code != "en":
        fallback_codes.append("en")
    if language_code != "zh":
        fallback_codes.append("zh")

    for code in fallback_codes:
        text = description.get(code)
        if isinstance(text, str):
            return text

    for value in description.values():
        if isinstance(value, str):
            return value
    return "N/A"
