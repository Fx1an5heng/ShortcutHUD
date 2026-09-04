"""Reconcile hook-derived modifier state with Windows physical key state.

The global hook remains the source of key-down intent.  This module only
removes logical modifiers that the hook still considers active after both of
their physical left/right keys are up; it never invents a missed key-down.
"""

from __future__ import annotations

import ctypes
from collections.abc import Iterable
from ctypes import wintypes
from typing import Callable, Final, Protocol


VK_LWIN: Final[int] = 0x5B
VK_RWIN: Final[int] = 0x5C
VK_LSHIFT: Final[int] = 0xA0
VK_RSHIFT: Final[int] = 0xA1
VK_LCONTROL: Final[int] = 0xA2
VK_RCONTROL: Final[int] = 0xA3
VK_LMENU: Final[int] = 0xA4
VK_RMENU: Final[int] = 0xA5

_KEY_CURRENTLY_DOWN_MASK: Final[int] = 0x8000
_LOGICAL_MODIFIER_VKS: Final[tuple[tuple[str, tuple[int, int]], ...]] = (
    ("ctrl", (VK_LCONTROL, VK_RCONTROL)),
    ("alt", (VK_LMENU, VK_RMENU)),
    ("shift", (VK_LSHIFT, VK_RSHIFT)),
    ("win", (VK_LWIN, VK_RWIN)),
)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_get_async_key_state = _user32.GetAsyncKeyState
_get_async_key_state.argtypes = (ctypes.c_int,)
_get_async_key_state.restype = wintypes.SHORT


class PhysicalModifierStateReader(Protocol):
    """Read one side-aware snapshot of currently held logical modifiers."""

    def read_pressed_modifiers(self) -> frozenset[str] | None: ...


class WindowsPhysicalModifierStateReader:
    """Read left/right modifier state through ``GetAsyncKeyState``.

    Only the high-order bit is used.  A read failure returns ``None`` so the
    caller can preserve internal state and retry instead of clearing it from a
    partial or unavailable snapshot.
    """

    def __init__(
        self,
        get_async_key_state: Callable[[int], int] | None = None,
    ) -> None:
        self._get_async_key_state = get_async_key_state or _get_async_key_state

    def read_pressed_modifiers(self) -> frozenset[str] | None:
        pressed: set[str] = set()
        try:
            for modifier, virtual_keys in _LOGICAL_MODIFIER_VKS:
                if any(
                    int(self._get_async_key_state(vk))
                    & _KEY_CURRENTLY_DOWN_MASK
                    for vk in virtual_keys
                ):
                    pressed.add(modifier)
        except Exception:
            return None
        return frozenset(pressed)


class PhysicalModifierReconciler:
    """Remove stale logical modifiers using an independent physical snapshot."""

    def __init__(
        self,
        state_reader: PhysicalModifierStateReader | None = None,
    ) -> None:
        self._state_reader = state_reader or WindowsPhysicalModifierStateReader()

    def reconcile(
        self,
        internal_modifiers: Iterable[str],
        *,
        only: Iterable[str] | None = None,
    ) -> set[str]:
        """Return internal state with physically released modifiers removed.

        ``only`` narrows correction to selected logical modifiers.  This is
        used by the explicit Win-release bridge, whose evidence concerns Win
        only; the periodic pass reconciles the complete internal set.
        """

        internal = set(internal_modifiers)
        physical = self._state_reader.read_pressed_modifiers()
        if physical is None:
            return internal

        candidates = internal if only is None else internal.intersection(only)
        return internal.difference(candidates.difference(physical))
