"""UI-independent, modifier-triggered shortcut resolution for ShortcutHUD.

The upstream virtual keyboard supports a ``NoModifier`` state, but Phase 1 of
ShortcutHUD intentionally does not resolve it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Literal, TypeAlias

from .modifier_state import (
    canonicalize_modifier_state,
    normalize_modifier_combination,
    normalize_modifier_token,
)


ShortcutSource: TypeAlias = Literal["APP", "DEFAULT", "GLOBAL"]

_DEFAULT_LAYER = "DEFAULT"
_GLOBAL_LAYER = "GLOBAL"
_RESERVED_LAYERS = frozenset({_DEFAULT_LAYER, _GLOBAL_LAYER})


@dataclass(frozen=True, slots=True)
class ShortcutEntry:
    """One resolved shortcut, retaining its original description value."""

    key: str
    description: object
    source: ShortcutSource


def _normalize_executable_name(executable: str | None) -> str | None:
    if not isinstance(executable, str):
        return None

    value = executable.strip().strip('"')
    if not value:
        return None
    return PureWindowsPath(value).name.upper()


def _find_application_layer(
    shortcut_data: Mapping[str, object],
    foreground_executable: str | None,
) -> Mapping[str, object] | None:
    executable_name = _normalize_executable_name(foreground_executable)
    if executable_name is None or executable_name in _RESERVED_LAYERS:
        return None

    for configured_name, layer in shortcut_data.items():
        if not isinstance(configured_name, str):
            continue
        if configured_name.upper() in _RESERVED_LAYERS:
            continue
        if configured_name.upper() == executable_name and isinstance(layer, Mapping):
            return layer
    return None


def _find_reserved_layer(
    shortcut_data: Mapping[str, object],
    layer_name: str,
) -> Mapping[str, object] | None:
    for configured_name, layer in shortcut_data.items():
        if (
            isinstance(configured_name, str)
            and configured_name.upper() == layer_name
            and isinstance(layer, Mapping)
        ):
            return layer
    return None


def _iter_layer_shortcuts(
    layer: Mapping[str, object],
    canonical_modifier: str,
) -> Iterator[tuple[str, object]]:
    """Yield matching shortcut items in their original configuration order."""

    for configured_modifier, shortcuts in layer.items():
        if not isinstance(configured_modifier, str):
            continue
        if not isinstance(shortcuts, Mapping):
            continue

        normalized_modifier = normalize_modifier_combination(configured_modifier)
        if normalized_modifier == canonical_modifier:
            for key, description in shortcuts.items():
                if isinstance(key, str):
                    yield key, description
            continue

        chord_modifier = _get_chord_base_modifier(configured_modifier)
        if chord_modifier != canonical_modifier:
            continue

        for key, description in shortcuts.items():
            if not isinstance(key, str):
                continue
            full_key = configured_modifier if not key else f"{configured_modifier} {key}"
            yield full_key, description


def _get_chord_base_modifier(configured_name: str) -> str | None:
    """Return modifiers held for a legacy multi-stroke shortcut group.

    The current JSON contains entries shaped like
    ``"Ctrl+K Ctrl+S": {"": description}``. They are shortcut keys rather
    than modifier-group names, so the complete configured string must survive
    resolution even though no virtual keycap can represent it.
    """

    strokes = configured_name.split()
    if len(strokes) < 2:
        return None

    modifier_tokens: list[str] = []
    has_non_modifier_key = False
    for token in strokes[0].split("+"):
        normalized_token = normalize_modifier_token(token)
        if normalized_token is None:
            has_non_modifier_key = True
        else:
            modifier_tokens.append(token)

    if not modifier_tokens or not has_non_modifier_key:
        return None
    return canonicalize_modifier_state(modifier_tokens)


def resolve_shortcuts(
    shortcut_data: Mapping[str, object],
    foreground_executable: str | None,
    modifier_combination: str | None,
) -> list[ShortcutEntry]:
    """Resolve shortcuts using APP/DEFAULT/GLOBAL layer semantics.

    Known applications resolve as ``APP + GLOBAL``. Unknown applications
    resolve as ``DEFAULT + GLOBAL``. The base layer wins case-insensitive key
    conflicts over GLOBAL, and configuration insertion order is preserved
    within each layer. Shortcut keys are treated as opaque strings; this module
    does not know whether a UI has a corresponding virtual keycap.
    ``NoModifier`` is outside this Phase 1 modifier-triggered resolver contract.
    """

    if not isinstance(shortcut_data, Mapping):
        return []

    canonical_modifier = normalize_modifier_combination(modifier_combination)
    if canonical_modifier is None:
        return []

    application_layer = _find_application_layer(
        shortcut_data,
        foreground_executable,
    )
    if application_layer is not None:
        base_layer = application_layer
        base_source: ShortcutSource = "APP"
    else:
        base_layer = _find_reserved_layer(shortcut_data, _DEFAULT_LAYER)
        base_source = "DEFAULT"

    global_layer = _find_reserved_layer(shortcut_data, _GLOBAL_LAYER)
    layers: tuple[
        tuple[Mapping[str, object] | None, ShortcutSource], ...
    ] = (
        (base_layer, base_source),
        (global_layer, "GLOBAL"),
    )

    resolved: list[ShortcutEntry] = []
    seen_keys: set[str] = set()

    for layer, source in layers:
        if layer is None:
            continue
        for key, description in _iter_layer_shortcuts(layer, canonical_modifier):
            key_identity = key.casefold()
            if key_identity in seen_keys:
                continue
            seen_keys.add(key_identity)
            resolved.append(
                ShortcutEntry(
                    key=key,
                    description=description,
                    source=source,
                )
            )

    return resolved
