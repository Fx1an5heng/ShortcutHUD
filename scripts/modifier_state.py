"""Pure helpers for canonical modifier-key combinations.

This module intentionally has no dependency on Qt, keyboard hooks, or UI code.
Its primary input contract is logical modifier tokens, not complete physical
key names that need normalization. It defines the canonical order used by
ShortcutHUD's logical layers while leaving physical-key interpretation to the
input adapter.

``NoModifier`` is a state supported by the upstream virtual keyboard, but
ShortcutHUD is currently a modifier-triggered product. The Phase 1 logic does
not resolve ``NoModifier`` as a modifier combination.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final


CANONICAL_MODIFIER_ORDER: Final[tuple[str, ...]] = (
    "Ctrl",
    "Alt",
    "Shift",
    "Win",
)

ALTGR_MODIFIER: Final[str] = "AltGr"

_MODIFIER_ALIASES: Final[dict[str, str]] = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
    "windows": "Win",
    "meta": "Win",
    "cmd": "Win",
    "command": "Win",
    "altgr": ALTGR_MODIFIER,
    "rightalt": ALTGR_MODIFIER,
}


def normalize_modifier_token(modifier: str) -> str | None:
    """Return one canonical modifier token, or ``None`` if unsupported.

    Spaces, underscores, and hyphens are ignored for alias matching so that
    values such as ``"right alt"`` can be recognized as ``AltGr``.
    """

    if not isinstance(modifier, str):
        return None

    compact_name = (
        modifier.strip()
        .casefold()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )
    if not compact_name:
        return None
    return _MODIFIER_ALIASES.get(compact_name)


def canonicalize_modifier_state(
    modifiers: Iterable[str],
    *,
    exclude_altgr: bool = False,
) -> str | None:
    """Convert a modifier collection to ShortcutHUD's canonical name.

    The canonical order is ``Ctrl -> Alt -> Shift -> Win``. Duplicate tokens
    are collapsed. An empty state returns ``None``.

    ``AltGr`` is deliberately not interpreted as ``Ctrl+Alt``. Phase 1 has not
    connected this helper to ``KeyboardHandler``: ``exclude_altgr`` is only an
    interface reserved for a future input adapter, and the current normal
    runtime path has no caller for it. If such an adapter explicitly passes
    ``exclude_altgr=True``, AltGr is ignored while any other held modifiers are
    preserved.
    """

    canonical_modifiers: set[str] = set()

    for modifier in modifiers:
        normalized = normalize_modifier_token(modifier)
        if normalized is None:
            return None
        if normalized == ALTGR_MODIFIER:
            if exclude_altgr:
                continue
            return None
        canonical_modifiers.add(normalized)

    ordered_modifiers = [
        modifier
        for modifier in CANONICAL_MODIFIER_ORDER
        if modifier in canonical_modifiers
    ]
    return "+".join(ordered_modifiers) if ordered_modifiers else None


def normalize_modifier_combination(
    combination: str | None,
    *,
    exclude_altgr: bool = False,
) -> str | None:
    """Normalize a configuration modifier name to canonical order.

    For example, ``"Shift+Alt"`` becomes ``"Alt+Shift"``. Empty or unknown
    combinations return ``None`` instead of raising, which lets callers treat
    unsupported configuration groups as non-matches. ``NoModifier`` is also
    unsupported by this Phase 1 modifier-triggered resolver contract.
    """

    if not isinstance(combination, str) or not combination.strip():
        return None

    tokens = [token.strip() for token in combination.split("+")]
    if any(not token for token in tokens):
        return None
    return canonicalize_modifier_state(tokens, exclude_altgr=exclude_altgr)
