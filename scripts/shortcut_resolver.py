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
from .shortcut_key import normalize_builtin_shortcut_identity


ShortcutSource: TypeAlias = Literal["USER_APP", "APP", "DEFAULT", "GLOBAL"]

_DEFAULT_LAYER = "DEFAULT"
_GLOBAL_LAYER = "GLOBAL"
_RESERVED_LAYERS = frozenset({_DEFAULT_LAYER, _GLOBAL_LAYER})
RESERVED_USER_IDENTITIES = frozenset(
    {
        _DEFAULT_LAYER,
        _GLOBAL_LAYER,
        "WINDOWS_SHELL",
        "SHELL_DESKTOP",
        "WPS_UNKNOWN",
    }
)
_GLOBAL_ONLY_IDENTITIES = frozenset({"WINDOWS_SHELL", "SHELL_DESKTOP", "WPS_UNKNOWN"})


@dataclass(frozen=True, slots=True)
class ShortcutEntry:
    """One resolved shortcut, retaining its original description value."""

    key: str
    description: object
    source: ShortcutSource


def normalize_application_identity(application: object) -> str | None:
    """Normalize one resolver-facing executable or logical application ID."""

    if not isinstance(application, str):
        return None

    value = application.strip().strip('"')
    if not value:
        return None
    return PureWindowsPath(value).name.upper()


def _find_application_layer(
    shortcut_data: Mapping[str, object],
    foreground_executable: str | None,
) -> Mapping[str, object] | None:
    executable_name = normalize_application_identity(foreground_executable)
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


def _find_user_profile(
    user_profiles: Mapping[str, object] | None,
    foreground_executable: str | None,
) -> Mapping[str, object] | None:
    if not isinstance(user_profiles, Mapping):
        return None

    application_id = normalize_application_identity(foreground_executable)
    if application_id is None or application_id in RESERVED_USER_IDENTITIES:
        return None

    for configured_name, profile in user_profiles.items():
        if not isinstance(configured_name, str) or not isinstance(profile, Mapping):
            continue
        if normalize_application_identity(configured_name) == application_id:
            return profile
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


def _profile_is_hidden_only(profile: Mapping[str, object]) -> bool:
    """Return whether stale suppression is the profile's only user-owned state."""

    display_name = profile.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return False
    shortcuts = profile.get("shortcuts")
    if isinstance(shortcuts, Mapping) and any(
        isinstance(group, Mapping) and bool(group) for group in shortcuts.values()
    ):
        return False
    hidden = profile.get("hidden_builtin")
    return isinstance(hidden, Mapping) and any(
        isinstance(group, list) and bool(group) for group in hidden.values()
    )


def _hidden_builtin_keys(
    profile: Mapping[str, object] | None,
    canonical_modifier: str,
) -> set[str]:
    """Return canonical APP terminal-key identities hidden for one modifier."""

    if profile is None:
        return set()
    hidden = profile.get("hidden_builtin")
    if not isinstance(hidden, Mapping):
        return set()

    identities: set[str] = set()
    for modifier, group in hidden.items():
        if not isinstance(group, list):
            continue
        if normalize_modifier_combination(modifier) != canonical_modifier:
            continue
        for key in group:
            try:
                _modifier, normalized_key = normalize_builtin_shortcut_identity(
                    canonical_modifier,
                    key,
                )
            except ValueError:
                continue
            identities.add(normalized_key.casefold())
    return identities


def resolve_shortcuts(
    shortcut_data: Mapping[str, object],
    foreground_executable: str | None,
    modifier_combination: str | None,
    user_profiles: Mapping[str, object] | None = None,
) -> list[ShortcutEntry]:
    """Resolve USER_APP/APP/DEFAULT/GLOBAL overlay semantics.

    A user profile overlays, rather than replaces, a matching built-in APP.
    A user-only profile is itself a known application and therefore never falls
    back to DEFAULT, except when its only state is stale APP suppression.
    WINDOWS_SHELL and WPS_UNKNOWN remain GLOBAL-only. Earlier layers win
    case-insensitive key conflicts and insertion order is preserved within each
    layer. Shortcut keys remain opaque display strings.
    ``NoModifier`` is outside this Phase 1 modifier-triggered resolver contract.
    """

    if not isinstance(shortcut_data, Mapping):
        return []

    canonical_modifier = normalize_modifier_combination(modifier_combination)
    if canonical_modifier is None:
        return []

    application_id = normalize_application_identity(foreground_executable)
    application_layer = _find_application_layer(
        shortcut_data,
        foreground_executable,
    )
    global_layer = _find_reserved_layer(shortcut_data, _GLOBAL_LAYER)
    layers: list[tuple[Mapping[str, object] | None, ShortcutSource]] = []
    user_profile: Mapping[str, object] | None = None

    if application_id not in _GLOBAL_ONLY_IDENTITIES:
        user_profile = _find_user_profile(user_profiles, foreground_executable)
        if (
            user_profile is not None
            and application_layer is None
            and _profile_is_hidden_only(user_profile)
        ):
            user_profile = None
        if user_profile is not None:
            user_shortcuts = user_profile.get("shortcuts")
            layers.append(
                (
                    user_shortcuts if isinstance(user_shortcuts, Mapping) else None,
                    "USER_APP",
                )
            )
            if application_layer is not None:
                layers.append((application_layer, "APP"))
        elif application_layer is not None:
            layers.append((application_layer, "APP"))
        else:
            layers.append(
                (
                    _find_reserved_layer(shortcut_data, _DEFAULT_LAYER),
                    "DEFAULT",
                )
            )

    layers.append((global_layer, "GLOBAL"))

    resolved: list[ShortcutEntry] = []
    seen_keys: set[str] = set()
    hidden_app_keys = _hidden_builtin_keys(user_profile, canonical_modifier)

    for layer, source in layers:
        if layer is None:
            continue
        for key, description in _iter_layer_shortcuts(layer, canonical_modifier):
            if source == "APP":
                try:
                    _modifier, canonical_key = normalize_builtin_shortcut_identity(
                        canonical_modifier,
                        key,
                    )
                except ValueError:
                    pass
                else:
                    if canonical_key.casefold() in hidden_app_keys:
                        continue
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
