"""Session-scoped Guide input ownership; passive outside the focused Guide."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Callable

from PySide6.QtCore import QObject, Signal

from .full_guide_model import MODIFIER_ORDER

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
PM_NOREMOVE = 0
LLKHF_INJECTED = 0x10

VK_LWIN, VK_RWIN = 0x5B, 0x5C
_WIN_VKS = frozenset({VK_LWIN, VK_RWIN})
_MODIFIER_VKS = {
    0xA2: "Ctrl", 0xA3: "Ctrl",
    0xA4: "Alt", 0xA5: "Alt",
    0xA0: "Shift", 0xA1: "Shift",
    VK_LWIN: "Win", VK_RWIN: "Win",
}

_ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
_LRESULT = ctypes.c_ssize_t


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


_HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
_user32.SetWindowsHookExW.restype = wintypes.HANDLE
_user32.CallNextHookEx.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_user32.CallNextHookEx.restype = _LRESULT
_user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetForegroundWindow.argtypes = ()
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
_user32.GetMessageW.restype = wintypes.BOOL
_user32.PeekMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.PostThreadMessageW.restype = wintypes.BOOL
_kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetCurrentThreadId.argtypes = ()
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class ModifierTapInterpreter:
    """Emit a modifier only when it was tapped without a terminal key."""

    def __init__(self) -> None:
        self._held: set[str] = set()
        self._tap_candidates: set[str] = set()

    def reset(self) -> None:
        self._held.clear()
        self._tap_candidates.clear()

    def handle(self, key_name: str, event_type: str) -> str | None:
        if key_name in MODIFIER_ORDER:
            if event_type == "down":
                if key_name not in self._held:
                    self._held.add(key_name)
                    self._tap_candidates.add(key_name)
                return None
            if event_type == "up" and key_name in self._held:
                self._held.remove(key_name)
                tapped = key_name in self._tap_candidates
                self._tap_candidates.discard(key_name)
                return key_name if tapped else None
            return None
        if event_type == "down":
            self._tap_candidates.difference_update(self._held)
        return None


class WindowsGuideWinInputBackend:
    """Suppress Win and Win chords only while the Guide owns foreground input."""

    def __init__(self, callback: Callable[[str, str], None], foreground_provider=None) -> None:
        self._callback = callback
        self._foreground_provider = foreground_provider or (lambda: int(_user32.GetForegroundWindow() or 0))
        self._lock = threading.Lock()
        self._active_hwnd = 0
        self._held_win: set[int] = set()
        self._owned_vks: set[int] = set()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._hook = None
        self._thread = None
        self._thread_id = None
        self._error = None
        self._hook_callback = _HOOKPROC(self._hook_proc)

    @property
    def last_error(self):
        return self._error

    def activate(self, hwnd: int) -> None:
        with self._lock:
            self._active_hwnd = int(hwnd or 0)
            self._held_win.clear()
            self._owned_vks.clear()

    def deactivate(self) -> None:
        with self._lock:
            self._active_hwnd = 0
            self._held_win.clear()
            self._owned_vks.clear()

    def start(self) -> bool:
        with self._lock:
            if self._hook is not None:
                return True
            if self._thread is not None:
                return False
            self._stop.clear()
            self._ready.clear()
            self._error = None
            self._thread = threading.Thread(target=self._thread_main, name="shortcut-hud-guide-input", daemon=True)
            thread = self._thread
        thread.start()
        if not self._ready.wait(timeout=5):
            self._error = TimeoutError("Timed out installing Guide input hook")
            self.stop()
            return False
        return self._hook is not None

    def stop(self) -> bool:
        self.deactivate()
        self._stop.set()
        thread, thread_id = self._thread, self._thread_id
        if thread_id is not None:
            _user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        return thread is None or not thread.is_alive()

    def process_event(self, vk: int, event_type: str, *, physical: bool = True, foreground_hwnd: int | None = None) -> bool:
        """Return True when this session owns and must suppress the event."""

        if not physical or event_type not in {"down", "up"}:
            return False
        with self._lock:
            active_hwnd = self._active_hwnd
        foreground = self._foreground_provider() if foreground_hwnd is None else foreground_hwnd
        if not active_hwnd or foreground != active_hwnd:
            return False

        callback = None
        with self._lock:
            if vk in _WIN_VKS:
                if event_type == "down":
                    first = vk not in self._owned_vks
                    self._held_win.add(vk)
                    self._owned_vks.add(vk)
                    callback = ("Win", "down") if first else None
                else:
                    self._held_win.discard(vk)
                    was_owned = vk in self._owned_vks
                    self._owned_vks.discard(vk)
                    callback = ("Win", "up") if was_owned else None
                owned = True
            elif self._held_win or vk in self._owned_vks:
                logical = _MODIFIER_VKS.get(vk, "")
                if event_type == "down":
                    first = vk not in self._owned_vks
                    self._owned_vks.add(vk)
                    callback = (logical, "down") if first else None
                else:
                    was_owned = vk in self._owned_vks
                    self._owned_vks.discard(vk)
                    callback = (logical, "up") if was_owned and logical else None
                owned = True
            else:
                owned = False
        if callback is not None:
            self._callback(*callback)
        return owned

    def _call_next(self, code, w_param, l_param):
        return int(_user32.CallNextHookEx(self._hook, code, w_param, l_param))

    def _hook_proc(self, code, w_param, l_param):
        if code != HC_ACTION or self._stop.is_set():
            return self._call_next(code, w_param, l_param)
        try:
            event = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            message = int(w_param)
            event_type = "down" if message in (WM_KEYDOWN, WM_SYSKEYDOWN) else "up" if message in (WM_KEYUP, WM_SYSKEYUP) else ""
            physical = not bool(event.flags & LLKHF_INJECTED)
            return 1 if self.process_event(int(event.vkCode), event_type, physical=physical) else self._call_next(code, w_param, l_param)
        except BaseException:
            return self._call_next(code, w_param, l_param)

    def _thread_main(self) -> None:
        try:
            self._thread_id = int(_kernel32.GetCurrentThreadId())
            message = wintypes.MSG()
            _user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)
            hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_callback, _kernel32.GetModuleHandleW(None), 0)
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self._hook = hook
            self._ready.set()
            while not self._stop.is_set():
                result = int(_user32.GetMessageW(ctypes.byref(message), None, 0, 0))
                if result == 0:
                    break
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
        except BaseException as error:
            self._error = error
            self._ready.set()
        finally:
            if self._hook:
                _user32.UnhookWindowsHookEx(self._hook)
            self._hook = self._thread = self._thread_id = None
            self._stop.set()
            self._ready.set()


class GuideWinInputService(QObject):
    key_event = Signal(str, str)

    def __init__(self, parent=None, backend=None) -> None:
        super().__init__(parent)
        self.backend = backend or WindowsGuideWinInputBackend(self.key_event.emit)
        if backend is not None:
            backend._callback = self.key_event.emit

    @property
    def last_error(self):
        return self.backend.last_error

    def start(self) -> bool:
        return self.backend.start()

    def stop(self) -> bool:
        return self.backend.stop()

    def activate(self, hwnd: int) -> None:
        self.backend.activate(hwnd)

    def deactivate(self) -> None:
        self.backend.deactivate()
