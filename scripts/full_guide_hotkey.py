"""One explicit Windows command, isolated from the passive keyboard hook."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QKeySequence

DEFAULT_GUIDE_HOTKEY = "Ctrl+Shift+F10"
GUIDE_HOTKEY_SETTING = "full_guide_hotkey"
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
_MODIFIERS = {"Alt": 1, "Ctrl": 2, "Shift": 4, "Meta": 8}
_NAMED_KEYS = {"Space": 0x20, "Tab": 9, "Return": 13, "Enter": 13, "Home": 0x24, "End": 0x23, "PgUp": 0x21, "PgDown": 0x22, "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "Insert": 0x2D, "Delete": 0x2E}


@dataclass(frozen=True, slots=True)
class HotkeySpec:
    text: str
    modifiers: int
    vk: int


def parse_hotkey(text: str) -> HotkeySpec:
    if not isinstance(text, str):
        raise ValueError("Use modifiers and a letter, number, function key or navigation key.")
    sequence = QKeySequence.fromString(text.replace("Win+", "Meta+"), QKeySequence.SequenceFormat.PortableText)
    if sequence.count() != 1:
        raise ValueError("Use one key combination.")
    canonical = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    parts = canonical.split("+")
    if len(parts) < 2 or any(part not in _MODIFIERS for part in parts[:-1]):
        raise ValueError("A modifier and a regular key are required.")
    modifiers = sum(_MODIFIERS[part] for part in set(parts[:-1]))
    key = parts[-1]
    if len(key) == 1 and key.isascii() and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        vk = _NAMED_KEYS.get(key, 0)
    # Win chords are OS-reserved; F12 is always debugger-reserved. Do not
    # register known system navigation/security commands, even if Windows
    # happens to permit overriding one in the current foreground context.
    if not vk or vk == 0x7B or modifiers & 8 or (modifiers, vk) in {(1, 9), (3, 0x2E), (6, 0x1B)}:
        raise ValueError("This key is unsupported or reserved by Windows.")
    return HotkeySpec(canonical, modifiers, vk)


class WindowsHotkeyBackend:
    def __init__(self) -> None:
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.api.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
        self.api.RegisterHotKey.restype = wintypes.BOOL
        self.api.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        self.api.UnregisterHotKey.restype = wintypes.BOOL
        self.api.GetAsyncKeyState.argtypes = (ctypes.c_int,)
        self.api.GetAsyncKeyState.restype = ctypes.c_short
        self.last_error = 0

    def register(self, identifier: int, spec: HotkeySpec) -> bool:
        success = bool(self.api.RegisterHotKey(None, identifier, spec.modifiers | MOD_NOREPEAT, spec.vk))
        self.last_error = 0 if success else ctypes.get_last_error()
        return success

    def unregister(self, identifier: int) -> None:
        self.api.UnregisterHotKey(None, identifier)

    def altgr_down(self) -> bool:
        return bool(self.api.GetAsyncKeyState(0xA5) & 0x8000)


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, service: "FullGuideHotkey") -> None:
        super().__init__()
        self.service = service

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) not in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            return False, 0
        native = wintypes.MSG.from_address(int(message))
        if native.message == WM_HOTKEY and self.service.handle_message(int(native.wParam)):
            return True, 0
        return False, 0


class FullGuideHotkey(QObject):
    activated = Signal()

    def __init__(self, application, parent=None, *, backend=None) -> None:
        super().__init__(parent)
        self.application = application
        self.backend = backend or WindowsHotkeyBackend()
        self.spec: HotkeySpec | None = None
        self.identifier: int | None = None
        self.last_error = ""
        self._filter = _HotkeyFilter(self)
        application.installNativeEventFilter(self._filter)

    def configure(self, text: str) -> bool:
        try:
            spec = parse_hotkey(text)
        except ValueError as error:
            self.last_error = str(error)
            return False
        if self.spec == spec:
            self.last_error = ""
            return True
        identifier = 0x5348 if self.identifier != 0x5348 else 0x5349
        if not self.backend.register(identifier, spec):
            self.last_error = f"RegisterHotKey failed ({self.backend.last_error})"
            return False
        previous = self.identifier
        self.identifier, self.spec, self.last_error = identifier, spec, ""
        if previous is not None:
            self.backend.unregister(previous)
        return True

    def handle_message(self, identifier: int) -> bool:
        if identifier != self.identifier or self.spec is None:
            return False
        # AltGr must never activate an explicit command while typing text.
        if not self.backend.altgr_down():
            self.activated.emit()
        return True

    def close(self) -> None:
        if self.identifier is not None:
            self.backend.unregister(self.identifier)
        self.identifier, self.spec = None, None
        self.application.removeNativeEventFilter(self._filter)
