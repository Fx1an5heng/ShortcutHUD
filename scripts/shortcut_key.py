"""Shared canonicalization for Phase 5B single-step terminal keys."""

from __future__ import annotations

import re
from typing import Final

from .modifier_state import normalize_modifier_combination


class ShortcutKeyError(ValueError):
    """Base error for values that cannot enter the single-step USER schema."""


class InvalidShortcutKeyError(ShortcutKeyError):
    """The value is not a recognized single keyboard key."""


class ModifierTerminalKeyError(ShortcutKeyError):
    """A modifier was entered in the terminal-key field."""

    def __init__(self, modifier: str) -> None:
        self.modifier = modifier
        super().__init__(f"modifier entered as terminal key: {modifier}")


class UnsupportedShortcutSequenceError(ShortcutKeyError):
    """A valid multi-step/chord pattern is outside the Phase 5B schema."""


_FUNCTION_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"f([0-9]+)",
    re.IGNORECASE,
)

_SPECIAL_KEY_ALIASES: Final[dict[str, str]] = {
    "tab": "Tab",
    "enter": "Enter",
    "return": "Enter",
    "esc": "Esc",
    "escape": "Esc",
    "space": "Space",
    "spacebar": "Space",
    "backspace": "Backspace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "ins": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pgup": "PageUp",
    "pagedown": "PageDown",
    "pgdn": "PageDown",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    # Existing built-in profiles use mouse buttons as single terminal inputs.
    # Keep the shared USER validator compatible with that established key
    # inventory even though most entries are ordinary keyboard keys.
    "lmb": "LMB",
    "mmb": "MMB",
    "rmb": "RMB",
}

_MODIFIER_KEY_ALIASES: Final[dict[str, str]] = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
    "windows": "Win",
}

# Printable keys on the standard main keyboard block. Shifted glyphs remain
# opaque terminal-key labels because the Modifier field owns the logical Shift.
_SYMBOL_KEYS: Final[frozenset[str]] = frozenset(
    "`-=[]\\;',./~_+{}|:\"<>?!@#$%^&*()"
)


def normalize_shortcut_key(key: object) -> str:
    """Return one canonical terminal key for the Phase 5B USER schema.

    This accepts a single keyboard key only. Multi-step/chord shortcuts are a
    legitimate future product feature, but they cannot be represented safely by
    the current ``Modifier + Key`` schema and therefore raise a distinct error.
    """

    if not isinstance(key, str) or not key.strip():
        raise InvalidShortcutKeyError("shortcut key must not be empty")

    value = key.strip()
    if _looks_like_multi_step_shortcut(value):
        raise UnsupportedShortcutSequenceError(
            "multi-step/chord shortcuts are not supported by this schema"
        )

    folded = value.casefold()
    modifier = _MODIFIER_KEY_ALIASES.get(folded)
    if modifier is not None:
        raise ModifierTerminalKeyError(modifier)

    special_key = _SPECIAL_KEY_ALIASES.get(folded)
    if special_key is not None:
        return special_key

    if len(value) == 1:
        if "a" <= folded <= "z":
            return folded.upper()
        if value.isascii() and value.isdigit():
            return value
        if value in _SYMBOL_KEYS:
            return value

    function_key = _FUNCTION_KEY_PATTERN.fullmatch(value)
    if function_key is not None:
        number = int(function_key.group(1))
        if 1 <= number <= 24:
            return f"F{number}"

    raise InvalidShortcutKeyError(f"unrecognized single keyboard key: {value!r}")


def normalize_builtin_shortcut_identity(
    modifier: object,
    key: object,
) -> tuple[str, str]:
    """Compose the existing modifier and terminal-key canonicalizers."""

    canonical_modifier = normalize_modifier_combination(modifier)
    if canonical_modifier is None:
        raise ValueError("modifier must be a supported modifier combination")
    return canonical_modifier, normalize_shortcut_key(key)


def _looks_like_multi_step_shortcut(value: str) -> bool:
    if any(character.isspace() for character in value):
        return True
    if "," in value and value != ",":
        return True
    return (
        len(value) == 2
        and value[0].isascii()
        and value[0].isalpha()
        and value[0].casefold() == value[1].casefold()
    )
