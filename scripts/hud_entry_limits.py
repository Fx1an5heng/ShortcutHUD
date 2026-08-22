"""Centralized visible-entry limits for the compact ShortcutHUD."""

from __future__ import annotations

from pathlib import PureWindowsPath

from .modifier_state import normalize_modifier_combination


DEFAULT_HUD_ENTRY_LIMIT = 8

HUD_ENTRY_LIMIT_OVERRIDES: dict[tuple[str, str], int] = {
    ("MSEDGE.EXE", "Ctrl"): 9,
    ("CHROME.EXE", "Ctrl"): 9,
}


def _normalize_executable_name(executable: str | None) -> str | None:
    if not isinstance(executable, str):
        return None

    value = executable.strip().strip('"')
    if not value:
        return None
    return PureWindowsPath(value).name.upper()


def get_hud_entry_limit(
    foreground_executable: str | None,
    modifier_combination: str | None,
) -> int:
    """Return the visible-row limit for a normalized app/modifier pair.

    Unknown or malformed inputs deliberately fall back to the product-wide
    default. This policy affects presentation only; shortcut resolution and
    APP/DEFAULT/GLOBAL layer semantics remain unchanged.
    """

    executable_name = _normalize_executable_name(foreground_executable)
    canonical_modifier = normalize_modifier_combination(modifier_combination)
    if executable_name is None or canonical_modifier is None:
        return DEFAULT_HUD_ENTRY_LIMIT
    return HUD_ENTRY_LIMIT_OVERRIDES.get(
        (executable_name, canonical_modifier),
        DEFAULT_HUD_ENTRY_LIMIT,
    )
