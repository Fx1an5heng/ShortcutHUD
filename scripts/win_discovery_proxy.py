"""Narrow Windows-key input proxy for an active ShortcutHUD discovery hold.

The hook is installed once and is passive by default.  A controller may arm one
physical left/right Win hold after its discovery threshold.  From that point
until the matching physical Win-up, only that Win key is proxied; every other
keyboard event is passed through unchanged.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Callable


WH_KEYBOARD_LL = 13
HC_ACTION = 0

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
PM_NOREMOVE = 0x0000

VK_LWIN = 0x5B
VK_RWIN = 0x5C
_VK_DUMMY = 0xFF

_LLKHF_INJECTED = 0x10

_INPUT_KEYBOARD = 1
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002

# Exact matching, rather than LLKHF_INJECTED alone, prevents recursion without
# mistaking another program's injected keyboard events for ShortcutHUD's own.
SELF_INJECTED_EXTRA_INFO = 0x53485750

_ULONG_PTR = (
    ctypes.c_ulonglong
    if ctypes.sizeof(ctypes.c_void_p) == 8
    else ctypes.c_ulong
)
_LRESULT = ctypes.c_ssize_t


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    )


class _INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = (("type", wintypes.DWORD), ("value", _INPUTUNION))


_HOOKPROC = ctypes.WINFUNCTYPE(
    _LRESULT,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    _HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
)
_user32.SetWindowsHookExW.restype = wintypes.HANDLE
_user32.CallNextHookEx.argtypes = (
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
_user32.CallNextHookEx.restype = _LRESULT
_user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
_user32.GetAsyncKeyState.restype = wintypes.SHORT
_user32.SendInput.argtypes = (
    wintypes.UINT,
    ctypes.POINTER(_INPUT),
    ctypes.c_int,
)
_user32.SendInput.restype = wintypes.UINT
_user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
_user32.GetMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.TranslateMessage.restype = wintypes.BOOL
_user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
_user32.DispatchMessageW.restype = _LRESULT
_user32.PeekMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
)
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
_user32.PostThreadMessageW.restype = wintypes.BOOL

_kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetCurrentThreadId.argtypes = ()
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def _is_down_message(message: int) -> bool:
    return message in (WM_KEYDOWN, WM_SYSKEYDOWN)


def _is_up_message(message: int) -> bool:
    return message in (WM_KEYUP, WM_SYSKEYUP)


def _keyboard_input(vk: int, flags: int, extra_info: int = 0) -> _INPUT:
    item = _INPUT()
    item.type = _INPUT_KEYBOARD
    item.ki = _KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=flags,
        time=0,
        dwExtraInfo=extra_info,
    )
    return item


class WinDiscoveryProxy:
    """Proxy exactly one physical Win hold while discovery is active."""

    def __init__(
        self,
        on_physical_win_released: Callable[[int], None] | None = None,
    ) -> None:
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._hook_ready = threading.Event()
        self._on_physical_win_released = on_physical_win_released

        self._hook_handle: wintypes.HANDLE | None = None
        self._hook_thread: threading.Thread | None = None
        self._hook_thread_id: int | None = None
        self._hook_error: BaseException | None = None

        self._physical_win_vks: set[int] = set()
        self._active_win_vk: int | None = None

        # Native code retains this function pointer until the hook is removed.
        self._hook_callback = _HOOKPROC(self._low_level_keyboard_proc)

    @property
    def last_error(self) -> BaseException | None:
        with self._state_lock:
            return self._hook_error

    def start(self) -> bool:
        """Install the permanent hook once; return False without blocking input."""

        with self._state_lock:
            if self._hook_handle is not None:
                return True
            if self._hook_thread is not None:
                return False
            self._stop_event.clear()
            self._hook_ready.clear()
            self._hook_error = None
            thread = threading.Thread(
                target=self._hook_thread_main,
                name="shortcut-hud-win-proxy",
                daemon=True,
            )
            self._hook_thread = thread

        thread.start()
        if not self._hook_ready.wait(timeout=5.0):
            with self._state_lock:
                self._hook_error = TimeoutError(
                    "Timed out while installing the Win discovery hook"
                )
            self.stop()
            return False

        with self._state_lock:
            return self._hook_handle is not None

    def stop(self) -> bool:
        """Stop the message pump and unhook without injecting cleanup input."""

        self._stop_event.set()
        with self._state_lock:
            thread = self._hook_thread
            thread_id = self._hook_thread_id

        if thread_id is not None:
            _user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)

        with self._state_lock:
            self._active_win_vk = None
            self._physical_win_vks.clear()
            return thread is None or not thread.is_alive()

    def current_physical_win_vk(self) -> int | None:
        """Return the currently held physical Win side, preferring left."""

        with self._state_lock:
            for win_vk in (VK_LWIN, VK_RWIN):
                if (
                    win_vk in self._physical_win_vks
                    and self._is_physical_key_down(win_vk)
                ):
                    return win_vk
        return None

    def activate_for_current_hold(self, win_vk: int) -> bool:
        """Arm one already-observed physical Win hold.

        The lock makes the final physical-state check atomic with respect to the
        hook's Win-up state update.  If Win-up wins the race, activation fails;
        if activation wins, the waiting Win-up callback completes the session.
        """

        if win_vk not in (VK_LWIN, VK_RWIN):
            return False

        with self._state_lock:
            if self._stop_event.is_set() or self._hook_handle is None:
                return False
            if self._active_win_vk is not None:
                return self._active_win_vk == win_vk
            if (
                win_vk not in self._physical_win_vks
                or not self._is_physical_key_down(win_vk)
            ):
                return False
            self._active_win_vk = win_vk
            return True

    @staticmethod
    def _is_physical_key_down(win_vk: int) -> bool:
        try:
            return bool(_user32.GetAsyncKeyState(win_vk) & 0x8000)
        except (OSError, ValueError):
            return False

    def _call_next(self, code: int, w_param: int, l_param: int) -> int:
        return int(
            _user32.CallNextHookEx(
                self._hook_handle,
                code,
                w_param,
                l_param,
            )
        )

    @staticmethod
    def _send_one(item: _INPUT) -> bool:
        inputs = (_INPUT * 1)(item)
        try:
            sent = int(_user32.SendInput(1, inputs, ctypes.sizeof(_INPUT)))
        except (OSError, ValueError):
            return False
        return sent == 1

    def _inject_win(self, win_vk: int, *, is_up: bool) -> bool:
        flags = _KEYEVENTF_EXTENDEDKEY
        if is_up:
            flags |= _KEYEVENTF_KEYUP
        return self._send_one(
            _keyboard_input(win_vk, flags, SELF_INJECTED_EXTRA_INFO)
        )

    def _notify_physical_win_released(self, win_vk: int) -> None:
        callback = self._on_physical_win_released
        if callback is None:
            return
        try:
            callback(win_vk)
        except Exception:
            # A consumer failure must never strand or swallow system input.
            pass

    def _proxy_win_down(
        self,
        win_vk: int,
        code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        if self._stop_event.is_set():
            return self._call_next(code, w_param, l_param)
        if not self._inject_win(win_vk, is_up=False):
            return self._call_next(code, w_param, l_param)
        return 1

    def _proxy_win_up(
        self,
        win_vk: int,
        code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        if self._stop_event.is_set():
            return self._call_next(code, w_param, l_param)

        # Verified PowerToys ordering: dummy key-up only, then same-side Win-up.
        dummy_ok = self._send_one(
            _keyboard_input(_VK_DUMMY, _KEYEVENTF_KEYUP)
        )
        win_up_ok = self._inject_win(win_vk, is_up=True)

        with self._state_lock:
            if self._active_win_vk == win_vk:
                self._active_win_vk = None

        # Physical release is true even when SendInput later fails open.
        # main.py queues this lightweight callback onto the Qt thread.
        self._notify_physical_win_released(win_vk)

        if not (dummy_ok and win_up_ok):
            return self._call_next(code, w_param, l_param)
        return 1

    def _low_level_keyboard_proc(
        self,
        code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        if code != HC_ACTION or self._stop_event.is_set():
            return self._call_next(code, w_param, l_param)

        try:
            event = ctypes.cast(
                l_param,
                ctypes.POINTER(_KBDLLHOOKSTRUCT),
            ).contents
            message = int(w_param)
            if not (_is_down_message(message) or _is_up_message(message)):
                return self._call_next(code, w_param, l_param)

            if int(event.dwExtraInfo) == SELF_INJECTED_EXTRA_INFO:
                return self._call_next(code, w_param, l_param)

            win_vk = int(event.vkCode)
            if win_vk not in (VK_LWIN, VK_RWIN):
                return self._call_next(code, w_param, l_param)

            # Third-party injected input is never treated as physical state and
            # is passed unchanged rather than being mistaken for our own input.
            is_physical = not bool(event.flags & _LLKHF_INJECTED)
            if not is_physical:
                return self._call_next(code, w_param, l_param)

            is_down = _is_down_message(message)
            with self._state_lock:
                if is_down:
                    self._physical_win_vks.add(win_vk)
                else:
                    self._physical_win_vks.discard(win_vk)
                active_win_vk = self._active_win_vk

            if active_win_vk != win_vk:
                return self._call_next(code, w_param, l_param)
            if is_down:
                return self._proxy_win_down(win_vk, code, w_param, l_param)
            return self._proxy_win_up(win_vk, code, w_param, l_param)
        except BaseException:
            # Hook callbacks must fail open so unexpected errors cannot strand
            # or swallow normal keyboard input.
            return self._call_next(code, w_param, l_param)

    def _hook_thread_main(self) -> None:
        try:
            thread_id = int(_kernel32.GetCurrentThreadId())
            message = wintypes.MSG()
            _user32.PeekMessageW(
                ctypes.byref(message),
                None,
                0,
                0,
                PM_NOREMOVE,
            )

            module = _kernel32.GetModuleHandleW(None)
            ctypes.set_last_error(0)
            hook = _user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._hook_callback,
                module,
                0,
            )
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())

            with self._state_lock:
                self._hook_thread_id = thread_id
                self._hook_handle = hook
            self._hook_ready.set()

            while not self._stop_event.is_set():
                result = int(
                    _user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                )
                if result == 0:
                    break
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                _user32.TranslateMessage(ctypes.byref(message))
                _user32.DispatchMessageW(ctypes.byref(message))
        except BaseException as error:
            with self._state_lock:
                self._hook_error = error
            self._hook_ready.set()
        finally:
            with self._state_lock:
                hook = self._hook_handle
            if hook:
                _user32.UnhookWindowsHookEx(hook)
            with self._state_lock:
                self._hook_handle = None
                self._hook_thread_id = None
                self._hook_thread = None
                self._active_win_vk = None
                self._physical_win_vks.clear()
            self._stop_event.set()
            self._hook_ready.set()
