"""Lightweight logical identities for Windows Explorer-owned surfaces."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import PureWindowsPath
from typing import Callable


EXPLORER_EXECUTABLE = "EXPLORER.EXE"
WINDOWS_SHELL = "WINDOWS_SHELL"

_FILE_EXPLORER_WINDOW_CLASSES = frozenset(
    {
        "cabinetwclass",
        "explorewclass",
    }
)
_USER32 = ctypes.WinDLL("user32", use_last_error=True)
_USER32.GetClassNameW.argtypes = (
    wintypes.HWND,
    wintypes.LPWSTR,
    ctypes.c_int,
)
_USER32.GetClassNameW.restype = ctypes.c_int


def get_window_class_name(hwnd: int) -> str | None:
    """Return the top-level Win32 class, or ``None`` on any read failure."""

    if not isinstance(hwnd, int) or hwnd <= 0:
        return None

    buffer = ctypes.create_unicode_buffer(256)
    try:
        copied = _USER32.GetClassNameW(
            wintypes.HWND(hwnd),
            buffer,
            len(buffer),
        )
    except BaseException:
        return None
    return buffer.value if copied > 0 else None


def classify_shell_application(
    executable: str | None,
    hwnd: int,
    window_class_provider: Callable[[int], str | None] = get_window_class_name,
) -> str | None:
    """Distinguish File Explorer windows from other explorer.exe surfaces.

    Ordinary applications pass through as normalized executable identities.
    An explorer.exe surface is a File Explorer APP only when its current
    top-level class is a known Explorer window class. Missing, unreadable, or
    unfamiliar class evidence fails closed to the empty WINDOWS_SHELL profile.
    """

    normalized_executable = _normalize_executable(executable)
    if normalized_executable != EXPLORER_EXECUTABLE:
        return normalized_executable

    try:
        window_class = window_class_provider(hwnd)
    except BaseException:
        window_class = None
    if (
        isinstance(window_class, str)
        and window_class.strip().casefold() in _FILE_EXPLORER_WINDOW_CLASSES
    ):
        return EXPLORER_EXECUTABLE
    return WINDOWS_SHELL


def _normalize_executable(executable: str | None) -> str | None:
    if not isinstance(executable, str):
        return None
    value = executable.strip().strip('"')
    if not value:
        return None
    return PureWindowsPath(value).name.upper()
