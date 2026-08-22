r"""Standalone Win-key proxy experiment for ShortcutHUD.

This spike intentionally has no imports from the application.  It installs a
permanent ``WH_KEYBOARD_LL`` hook, but remains passive until a physical left or
right Win key has been held for 300 ms.  It is a console diagnostic only.

Run from the repository root with::

    .\.venv\Scripts\python.exe -u spikes\win_key_proxy_spike.py

Press Ctrl+C to stop.  Shutdown only removes the hook; it never injects cleanup
keystrokes.
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import platform
import queue
import sys
import threading
import time
from typing import Final


if sys.platform != "win32":
    raise SystemExit("This spike only runs on Windows.")


WH_KEYBOARD_LL: Final = 13
HC_ACTION: Final = 0

WM_KEYDOWN: Final = 0x0100
WM_KEYUP: Final = 0x0101
WM_SYSKEYDOWN: Final = 0x0104
WM_SYSKEYUP: Final = 0x0105
WM_QUIT: Final = 0x0012

PM_NOREMOVE: Final = 0x0000

VK_SHIFT: Final = 0x10
VK_CONTROL: Final = 0x11
VK_MENU: Final = 0x12
VK_LSHIFT: Final = 0xA0
VK_RSHIFT: Final = 0xA1
VK_LCONTROL: Final = 0xA2
VK_RCONTROL: Final = 0xA3
VK_LMENU: Final = 0xA4
VK_RMENU: Final = 0xA5
VK_LWIN: Final = 0x5B
VK_RWIN: Final = 0x5C
VK_DUMMY: Final = 0xFF

LLKHF_INJECTED: Final = 0x10

INPUT_KEYBOARD: Final = 1
KEYEVENTF_EXTENDEDKEY: Final = 0x0001
KEYEVENTF_KEYUP: Final = 0x0002

CTRL_C_EVENT: Final = 0
CTRL_BREAK_EVENT: Final = 1
CTRL_CLOSE_EVENT: Final = 2
CTRL_LOGOFF_EVENT: Final = 5
CTRL_SHUTDOWN_EVENT: Final = 6

WIN_ONLY_SHOW_DELAY_MS: Final = 300

# Deliberately unique to this spike.  Exact matching is the only self-injection
# test; LLKHF_INJECTED alone must not hide another program's injected events.
SELF_INJECTED_EXTRA_INFO: Final = 0x53485750  # ASCII-ish: "SHWP"

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
LRESULT = ctypes.c_ssize_t


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUTUNION(ctypes.Union):
    _fields_ = (
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    )


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = (("type", wintypes.DWORD), ("value", INPUTUNION))


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
CONSOLE_HANDLER = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.SetWindowsHookExW.argtypes = (
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
)
user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.CallNextHookEx.argtypes = (
    wintypes.HANDLE,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = LRESULT
user32.PeekMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
)
user32.PeekMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = (
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostThreadMessageW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetCurrentThreadId.argtypes = ()
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.SetConsoleCtrlHandler.argtypes = (CONSOLE_HANDLER, wintypes.BOOL)
kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL


KEY_NAMES: Final = {
    VK_SHIFT: "SHIFT",
    VK_CONTROL: "CTRL",
    VK_MENU: "ALT",
    VK_LSHIFT: "LSHIFT",
    VK_RSHIFT: "RSHIFT",
    VK_LCONTROL: "LCTRL",
    VK_RCONTROL: "RCTRL",
    VK_LMENU: "LALT",
    VK_RMENU: "RALT",
    VK_LWIN: "LWIN",
    VK_RWIN: "RWIN",
    VK_DUMMY: "DUMMY_FF",
    0x09: "TAB",
    0x44: "D",
    0x45: "E",
    0x52: "R",
    0x56: "V",
}

MODIFIER_VKS: Final = {
    VK_SHIFT,
    VK_CONTROL,
    VK_MENU,
    VK_LSHIFT,
    VK_RSHIFT,
    VK_LCONTROL,
    VK_RCONTROL,
    VK_LMENU,
    VK_RMENU,
    VK_LWIN,
    VK_RWIN,
}


@dataclass(frozen=True)
class ProxySnapshot:
    proxy_active: bool
    physical_win_vk: int | None
    execution_seen: bool


@dataclass(frozen=True)
class ActivationRequest:
    generation: int
    win_vk: int
    deadline: float


@dataclass(frozen=True)
class LogRecord:
    timestamp: float
    kind: str
    message: str
    snapshot: ProxySnapshot


def _key_name(vk: int | None) -> str:
    if vk is None:
        return "NONE"
    if 0x30 <= vk <= 0x5A:
        return chr(vk)
    return KEY_NAMES.get(vk, f"VK_0x{vk:02X}")


def _is_key_down_message(message: int) -> bool:
    return message in (WM_KEYDOWN, WM_SYSKEYDOWN)


def _is_key_up_message(message: int) -> bool:
    return message in (WM_KEYUP, WM_SYSKEYUP)


def _keyboard_input(vk: int, flags: int, extra_info: int = 0) -> INPUT:
    item = INPUT()
    item.type = INPUT_KEYBOARD
    item.ki = KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=flags,
        time=0,
        dwExtraInfo=extra_info,
    )
    return item


class WinKeyProxySpike:
    def __init__(self) -> None:
        self._state_lock = threading.Lock()
        self._proxy_active = False
        self._physical_win_vk: int | None = None
        self._physical_down_at: float | None = None
        self._execution_seen = False
        self._generation = 0

        self._stop_event = threading.Event()
        self._hook_ready = threading.Event()
        self._hook_error: BaseException | None = None
        self._hook_handle: wintypes.HANDLE | None = None
        self._hook_thread_id: int | None = None

        self._activation_queue: queue.Queue[ActivationRequest | None] = queue.Queue()
        self._log_queue: queue.Queue[LogRecord | None] = queue.Queue()

        # Keep callback objects alive for as long as native code can call them.
        self._hook_callback = HOOKPROC(self._low_level_keyboard_proc)
        self._console_callback = CONSOLE_HANDLER(self._console_control_handler)

        self._hook_thread = threading.Thread(
            target=self._hook_thread_main,
            name="win-proxy-hook",
        )
        self._activation_thread = threading.Thread(
            target=self._activation_worker,
            name="win-proxy-threshold",
        )
        self._printer_thread = threading.Thread(
            target=self._printer_worker,
            name="win-proxy-logger",
        )

    def _snapshot(self) -> ProxySnapshot:
        with self._state_lock:
            return ProxySnapshot(
                proxy_active=self._proxy_active,
                physical_win_vk=self._physical_win_vk,
                execution_seen=self._execution_seen,
            )

    def _log(
        self,
        kind: str,
        message: str,
        snapshot: ProxySnapshot | None = None,
    ) -> None:
        self._log_queue.put_nowait(
            LogRecord(
                timestamp=time.perf_counter(),
                kind=kind,
                message=message,
                snapshot=snapshot if snapshot is not None else self._snapshot(),
            )
        )

    def _printer_worker(self) -> None:
        while True:
            record = self._log_queue.get()
            if record is None:
                return
            state = record.snapshot
            print(
                f"[{record.timestamp:012.6f}] [{record.kind}] {record.message} "
                f"proxy_active={state.proxy_active} "
                f"physical_win_vk={_key_name(state.physical_win_vk)} "
                f"execution_seen={state.execution_seen}",
                flush=True,
            )

    def _origin(self, event: KBDLLHOOKSTRUCT) -> str:
        if int(event.dwExtraInfo) == SELF_INJECTED_EXTRA_INFO:
            return "SELF_INJECTED"
        if event.flags & LLKHF_INJECTED:
            return "OTHER_INJECTED"
        return "PHYSICAL"

    def _call_next(self, code: int, w_param: int, l_param: int) -> int:
        return int(
            user32.CallNextHookEx(
                self._hook_handle,
                code,
                w_param,
                l_param,
            )
        )

    def _send_one(self, label: str, item: INPUT) -> bool:
        inputs = (INPUT * 1)(item)
        ctypes.set_last_error(0)
        sent = int(user32.SendInput(1, inputs, ctypes.sizeof(INPUT)))
        last_error = ctypes.get_last_error()
        self._log(
            "SENDINPUT",
            f"label={label} requested=1 returned={sent} GetLastError={last_error}",
        )
        return sent == 1

    def _inject_proxy_win(self, win_vk: int, *, is_up: bool) -> bool:
        flags = KEYEVENTF_EXTENDEDKEY
        if is_up:
            flags |= KEYEVENTF_KEYUP
        return self._send_one(
            "synthetic_win_up" if is_up else "synthetic_win_down",
            _keyboard_input(win_vk, flags, SELF_INJECTED_EXTRA_INFO),
        )

    def _handle_proxy_win_down(
        self,
        win_vk: int,
        code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        self._log("PROXY", f"swallow-real-down vk={_key_name(win_vk)}")
        injected = self._inject_proxy_win(win_vk, is_up=False)
        if not injected:
            self._log("PROXY", "synthetic down failed; fail-safe pass real event")
            return self._call_next(code, w_param, l_param)
        return 1

    def _handle_proxy_win_up(
        self,
        win_vk: int,
        code: int,
        w_param: int,
        l_param: int,
    ) -> int:
        self._log("PROXY", f"swallow-real-up vk={_key_name(win_vk)}")

        # Preserve the PowerToys order: harmless dummy key-up first, then the
        # synthetic up for the same side of Win.  Never hold the state lock
        # across SendInput because our own events re-enter this hook.
        dummy_ok = self._send_one(
            "dummy_ff_key_up",
            _keyboard_input(VK_DUMMY, KEYEVENTF_KEYUP),
        )
        win_up_ok = self._inject_proxy_win(win_vk, is_up=True)

        with self._state_lock:
            self._proxy_active = False
            self._physical_win_vk = None
            self._physical_down_at = None
            self._execution_seen = False
            self._generation += 1
            snapshot = ProxySnapshot(False, None, False)

        self._log("PROXY", "deactivate; physical Win session cleared", snapshot)

        if not (dummy_ok and win_up_ok):
            self._log("PROXY", "release injection failed; fail-safe pass real up")
            return self._call_next(code, w_param, l_param)
        return 1

    def _handle_non_win(self, vk: int, is_down: bool) -> None:
        with self._state_lock:
            if not self._proxy_active:
                return
            if is_down and vk not in MODIFIER_VKS:
                self._execution_seen = True
            snapshot = ProxySnapshot(
                self._proxy_active,
                self._physical_win_vk,
                self._execution_seen,
            )
        self._log(
            "NON-WIN",
            f"vk={_key_name(vk)} action={'down' if is_down else 'up'} pass-through",
            snapshot,
        )

    def _record_first_win_down(self, win_vk: int) -> None:
        now = time.perf_counter()
        request: ActivationRequest | None = None
        with self._state_lock:
            if self._physical_win_vk is None:
                self._physical_win_vk = win_vk
                self._physical_down_at = now
                self._execution_seen = False
                self._generation += 1
                request = ActivationRequest(
                    generation=self._generation,
                    win_vk=win_vk,
                    deadline=now + (WIN_ONLY_SHOW_DELAY_MS / 1000.0),
                )
                snapshot = ProxySnapshot(False, win_vk, False)
            else:
                snapshot = ProxySnapshot(
                    self._proxy_active,
                    self._physical_win_vk,
                    self._execution_seen,
                )

        if request is not None:
            self._activation_queue.put_nowait(request)
            self._log(
                "SESSION",
                f"first Win down vk={_key_name(win_vk)} threshold_ms={WIN_ONLY_SHOW_DELAY_MS}",
                snapshot,
            )

    def _finish_passive_win_tap(self, win_vk: int) -> None:
        now = time.perf_counter()
        with self._state_lock:
            if self._physical_win_vk != win_vk or self._proxy_active:
                return
            elapsed_ms = (
                (now - self._physical_down_at) * 1000.0
                if self._physical_down_at is not None
                else 0.0
            )
            self._physical_win_vk = None
            self._physical_down_at = None
            self._execution_seen = False
            self._generation += 1
            snapshot = ProxySnapshot(False, None, False)
        self._log(
            "SESSION",
            f"passive Win release vk={_key_name(win_vk)} elapsed_ms={elapsed_ms:.1f}",
            snapshot,
        )

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
                ctypes.POINTER(KBDLLHOOKSTRUCT),
            ).contents
            vk = int(event.vkCode)
            message = int(w_param)
            is_down = _is_key_down_message(message)
            is_up = _is_key_up_message(message)
            origin = self._origin(event)

            if not (is_down or is_up):
                return self._call_next(code, w_param, l_param)

            self._log(
                "EVENT",
                f"origin={origin} vk={_key_name(vk)}(0x{vk:02X}) "
                f"action={'down' if is_down else 'up'} flags=0x{int(event.flags):02X} "
                f"extra=0x{int(event.dwExtraInfo):X}",
            )

            # Exact self marker: pass through and do not mutate session state.
            if origin == "SELF_INJECTED":
                return self._call_next(code, w_param, l_param)

            if vk not in (VK_LWIN, VK_RWIN):
                self._handle_non_win(vk, is_down)
                return self._call_next(code, w_param, l_param)

            with self._state_lock:
                active = self._proxy_active
                physical_win_vk = self._physical_win_vk

            if active and vk == physical_win_vk:
                if is_down:
                    return self._handle_proxy_win_down(vk, code, w_param, l_param)
                return self._handle_proxy_win_up(vk, code, w_param, l_param)

            if not active and is_down:
                self._record_first_win_down(vk)
            elif not active and is_up:
                self._finish_passive_win_tap(vk)

            # Other-side Win and all passive Win events remain native.
            return self._call_next(code, w_param, l_param)
        except BaseException as error:
            # A hook callback must always fail open so it cannot strand input.
            try:
                self._log("ERROR", f"hook callback failed: {error!r}")
            finally:
                return self._call_next(code, w_param, l_param)

    def _activation_worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                request = self._activation_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if request is None:
                return

            delay = max(0.0, request.deadline - time.perf_counter())
            if self._stop_event.wait(delay):
                return

            still_down = bool(user32.GetAsyncKeyState(request.win_vk) & 0x8000)
            with self._state_lock:
                valid = (
                    not self._stop_event.is_set()
                    and self._generation == request.generation
                    and self._physical_win_vk == request.win_vk
                    and not self._proxy_active
                    and still_down
                )
                if valid:
                    self._proxy_active = True
                snapshot = ProxySnapshot(
                    self._proxy_active,
                    self._physical_win_vk,
                    self._execution_seen,
                )

            if valid:
                self._log(
                    "DISCOVERY ACTIVE",
                    f"vk={_key_name(request.win_vk)} physical_still_down=True",
                    snapshot,
                )
                self._log("PROXY", "activate", snapshot)
            else:
                self._log(
                    "THRESHOLD",
                    f"cancelled vk={_key_name(request.win_vk)} "
                    f"physical_still_down={still_down}",
                    snapshot,
                )

    def _hook_thread_main(self) -> None:
        try:
            self._hook_thread_id = int(kernel32.GetCurrentThreadId())
            message = wintypes.MSG()
            # Force creation of the thread message queue before another thread
            # can attempt PostThreadMessage(WM_QUIT).
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, PM_NOREMOVE)

            module = kernel32.GetModuleHandleW(None)
            ctypes.set_last_error(0)
            hook = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._hook_callback,
                module,
                0,
            )
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self._hook_handle = hook
            self._log("HOOK", f"installed thread_id={self._hook_thread_id}")
            self._hook_ready.set()

            while not self._stop_event.is_set():
                result = int(user32.GetMessageW(ctypes.byref(message), None, 0, 0))
                if result == 0:
                    break
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        except BaseException as error:
            self._hook_error = error
            self._log("ERROR", f"hook thread failed: {error!r}")
            self._stop_event.set()
            self._hook_ready.set()
        finally:
            hook = self._hook_handle
            self._hook_handle = None
            if hook:
                ctypes.set_last_error(0)
                removed = bool(user32.UnhookWindowsHookEx(hook))
                self._log(
                    "HOOK",
                    f"unhook requested=True returned={removed} "
                    f"GetLastError={ctypes.get_last_error()}",
                )
            self._stop_event.set()

    def _console_control_handler(self, control_type: int) -> bool:
        if control_type not in {
            CTRL_C_EVENT,
            CTRL_BREAK_EVENT,
            CTRL_CLOSE_EVENT,
            CTRL_LOGOFF_EVENT,
            CTRL_SHUTDOWN_EVENT,
        }:
            return False
        self.request_stop(f"console_control={control_type}")
        return True

    def request_stop(self, reason: str = "requested") -> None:
        first_request = not self._stop_event.is_set()
        self._stop_event.set()
        if first_request:
            self._log("SHUTDOWN", f"reason={reason}; no cleanup input will be injected")
        self._activation_queue.put_nowait(None)
        hook_thread_id = self._hook_thread_id
        if hook_thread_id is not None:
            user32.PostThreadMessageW(hook_thread_id, WM_QUIT, 0, 0)

    def run(self) -> None:
        self._printer_thread.start()
        self._activation_thread.start()

        if not kernel32.SetConsoleCtrlHandler(self._console_callback, True):
            raise ctypes.WinError(ctypes.get_last_error())
        atexit.register(self.request_stop, "atexit")

        try:
            self._hook_thread.start()
            if not self._hook_ready.wait(timeout=5.0):
                raise RuntimeError("Timed out while installing WH_KEYBOARD_LL")
            if self._hook_error is not None:
                raise RuntimeError("WH_KEYBOARD_LL installation failed") from self._hook_error

            print(
                "Win Key Proxy Spike is running. Hold LWin or RWin for 300 ms; "
                "press Ctrl+C to stop.",
                flush=True,
            )
            while not self._stop_event.wait(0.25):
                pass
        finally:
            self.request_stop("run-finally")
            if self._hook_thread.is_alive():
                self._hook_thread.join(timeout=3.0)
            if self._activation_thread.is_alive():
                self._activation_thread.join(timeout=3.0)
            kernel32.SetConsoleCtrlHandler(self._console_callback, False)
            atexit.unregister(self.request_stop)
            self._log_queue.put_nowait(None)
            self._printer_thread.join(timeout=3.0)


def _self_check() -> int:
    pointer_bits = ctypes.sizeof(ctypes.c_void_p) * 8
    expected_input_size = 40 if pointer_bits == 64 else 28
    expected_hook_size = 24 if pointer_bits == 64 else 20
    checks = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "pointer_bits": pointer_bits,
        "sizeof_INPUT": ctypes.sizeof(INPUT),
        "expected_INPUT": expected_input_size,
        "sizeof_KBDLLHOOKSTRUCT": ctypes.sizeof(KBDLLHOOKSTRUCT),
        "expected_KBDLLHOOKSTRUCT": expected_hook_size,
        "threshold_ms": WIN_ONLY_SHOW_DELAY_MS,
        "self_marker": f"0x{SELF_INJECTED_EXTRA_INFO:X}",
    }
    for name, value in checks.items():
        print(f"{name}={value}")
    ok = (
        ctypes.sizeof(INPUT) == expected_input_size
        and ctypes.sizeof(KBDLLHOOKSTRUCT) == expected_hook_size
        and WIN_ONLY_SHOW_DELAY_MS == 300
    )
    print(f"self_check={'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="validate ctypes layout and constants without installing a hook",
    )
    arguments = parser.parse_args()
    if arguments.self_check:
        return _self_check()

    spike = WinKeyProxySpike()
    spike.run()
    if spike._hook_error is not None:
        raise RuntimeError("Hook thread terminated with an error") from spike._hook_error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
