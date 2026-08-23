"""Foreground application identity coordination for ordinary apps and WPS."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import PureWindowsPath
import time
from typing import Callable, Protocol

from PySide6.QtCore import QObject, Qt, Signal, Slot

from .wps_identity import (
    HIGH_CONFIDENCE,
    WPS_PDF,
    WPS_PRESENTATION,
    WPS_UNKNOWN,
    WPS_WRITER,
    WpsIdentityRequest,
    WpsIdentityResult,
    WpsIdentityWorker,
)


EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_FOCUS = 0x8005
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
GA_ROOT = 2

_WPS_EXECUTABLE = "WPS.EXE"
_WPS_PROFILE_BY_LOGICAL_ID = {
    WPS_WRITER: WPS_WRITER,
    WPS_PDF: WPS_PDF,
    WPS_PRESENTATION: WPS_PRESENTATION,
    WPS_UNKNOWN: WPS_UNKNOWN,
}
_USER32 = ctypes.WinDLL("user32", use_last_error=True)
_USER32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
_USER32.GetAncestor.restype = wintypes.HWND
_USER32.UnhookWinEvent.argtypes = (wintypes.HANDLE,)
_USER32.UnhookWinEvent.restype = wintypes.BOOL


class _ForegroundMonitor(Protocol):
    current_hwnd: int
    current_app_name: str | None

    def check_foreground_app(self) -> bool: ...


class _IdentityWorker(Protocol):
    def start(self) -> None: ...

    def submit(self, request: WpsIdentityRequest) -> bool: ...

    def invalidate(self, generation: int) -> None: ...

    def stop_accepting_requests(self) -> None: ...

    def stop(self, timeout: float = 1.0) -> bool: ...


class WinEventHook:
    """Emit low-cost foreground/focus notifications; never performs UIA work."""

    _CALLBACK = ctypes.WINFUNCTYPE(
        None,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.HWND,
        wintypes.LONG,
        wintypes.LONG,
        wintypes.DWORD,
        wintypes.DWORD,
    )

    def __init__(self, callback: Callable[[int, int, int, int], None]) -> None:
        self._callback = callback
        self._callback_pointer = self._CALLBACK(self._on_event)
        self._hooks: list[int] = []
        self.last_error: int | None = None

    def start(self) -> bool:
        if self._hooks:
            return True

        user32 = _USER32
        user32.SetWinEventHook.argtypes = (
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            self._CALLBACK,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        )
        user32.SetWinEventHook.restype = wintypes.HANDLE

        flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
        for event in (EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_FOCUS):
            hook = user32.SetWinEventHook(
                event,
                event,
                None,
                self._callback_pointer,
                0,
                0,
                flags,
            )
            if not hook:
                self.last_error = ctypes.get_last_error()
                self.stop()
                return False
            self._hooks.append(int(hook))
        self.last_error = None
        return True

    def stop(self) -> None:
        user32 = _USER32
        for hook in self._hooks:
            try:
                user32.UnhookWinEvent(wintypes.HANDLE(hook))
            except BaseException:
                pass
        self._hooks.clear()

    def _on_event(
        self,
        _hook: int,
        event: int,
        hwnd: int,
        object_id: int,
        child_id: int,
        _event_thread: int,
        _event_time: int,
    ) -> None:
        try:
            self._callback(
                int(event),
                int(hwnd or 0),
                int(object_id),
                int(child_id),
            )
        except BaseException:
            # Native callbacks must never unwind into user32.
            return


class ApplicationIdentityRuntime(QObject):
    """Publish a resolver-facing app profile without blocking the Qt thread."""

    active_app_changed = Signal(str)
    identity_result_published = Signal(object)
    _worker_result_received = Signal(object)
    _windows_event_received = Signal(int, object, int, int)

    def __init__(
        self,
        foreground_monitor: _ForegroundMonitor,
        parent: QObject | None = None,
        worker: _IdentityWorker | None = None,
        event_hook_factory: Callable[
            [Callable[[int, int, int, int], None]], WinEventHook
        ] = WinEventHook,
    ) -> None:
        super().__init__(parent)
        self._foreground_monitor = foreground_monitor
        self._generation = 0
        self._current_hwnd = 0
        self._current_executable: str | None = None
        self.current_app_name: str | None = None
        self.current_logical_app_id: str | None = None
        self.identity_pending = False
        self.last_identity_result: WpsIdentityResult | None = None
        self._stopped = False

        self._worker = worker or WpsIdentityWorker(
            self._worker_result_received.emit
        )
        self._event_hook = event_hook_factory(
            self._windows_event_received.emit
        )
        self._worker_result_received.connect(
            self._on_worker_result,
            type=Qt.ConnectionType.QueuedConnection,
        )
        self._windows_event_received.connect(
            self._on_windows_event,
            type=Qt.ConnectionType.QueuedConnection,
        )

    def start(self) -> bool:
        self._stopped = False
        self._worker.start()
        return self._event_hook.start()

    @property
    def event_hook_error(self) -> int | None:
        return self._event_hook.last_error

    @Slot(object, object)
    def on_foreground_changed(
        self,
        hwnd: object,
        executable: object,
    ) -> None:
        if self._stopped:
            return

        normalized_executable = _normalize_executable(executable)
        normalized_hwnd = int(hwnd) if isinstance(hwnd, int) else 0
        self._current_hwnd = normalized_hwnd
        self._current_executable = normalized_executable

        if normalized_executable == _WPS_EXECUTABLE and normalized_hwnd > 0:
            self._request_wps_identity(normalized_hwnd)
            return

        self._generation += 1
        self._worker.invalidate(self._generation)
        self.identity_pending = False
        self.last_identity_result = None
        self.current_logical_app_id = normalized_executable
        self._publish_application(normalized_executable)

    @Slot(int, object, int, int)
    def _on_windows_event(
        self,
        event: int,
        event_hwnd: object,
        _object_id: int,
        _child_id: int,
    ) -> None:
        if self._stopped:
            return

        generation_before_refresh = self._generation
        self._foreground_monitor.check_foreground_app()
        executable = _normalize_executable(
            self._foreground_monitor.current_app_name
        )
        hwnd = int(self._foreground_monitor.current_hwnd or 0)
        if executable != _WPS_EXECUTABLE or hwnd <= 0:
            return

        if event == EVENT_OBJECT_FOCUS and isinstance(event_hwnd, int):
            if event_hwnd and not _belongs_to_root(event_hwnd, hwnd):
                return

        # A foreground change may already have synchronously emitted a request.
        if self._generation == generation_before_refresh:
            self._current_hwnd = hwnd
            self._current_executable = executable
            self._request_wps_identity(hwnd)

    def _request_wps_identity(self, hwnd: int) -> None:
        self._generation += 1
        generation = self._generation
        self.identity_pending = True
        self.last_identity_result = None
        self.current_logical_app_id = WPS_UNKNOWN
        self._publish_application(WPS_UNKNOWN, force=True)
        self._worker.submit(
            WpsIdentityRequest(
                hwnd=hwnd,
                generation=generation,
                requested_at=time.monotonic(),
            )
        )

    @Slot(object)
    def _on_worker_result(self, result: object) -> None:
        if self._stopped or not isinstance(result, WpsIdentityResult):
            return
        if (
            result.hwnd != self._current_hwnd
            or result.generation != self._generation
            or self._current_executable != _WPS_EXECUTABLE
        ):
            return

        logical_app_id = (
            result.logical_app_id
            if result.confidence == HIGH_CONFIDENCE
            and result.logical_app_id in _WPS_PROFILE_BY_LOGICAL_ID
            else WPS_UNKNOWN
        )
        self.identity_pending = False
        self.last_identity_result = result
        self.current_logical_app_id = logical_app_id
        self._publish_application(
            _WPS_PROFILE_BY_LOGICAL_ID[logical_app_id],
            force=True,
        )
        self.identity_result_published.emit(result)

    def stop_requests(self) -> None:
        self._stopped = True
        self.identity_pending = False
        self._generation += 1
        self._worker.stop_accepting_requests()
        self._worker.invalidate(self._generation)

    def stop_event_hook(self) -> None:
        self._event_hook.stop()

    def stop_worker(self, timeout: float = 1.0) -> bool:
        return self._worker.stop(timeout)

    def stop(self, timeout: float = 1.0) -> bool:
        self.stop_requests()
        self.stop_event_hook()
        return self.stop_worker(timeout)

    def _publish_application(
        self,
        application_name: str | None,
        force: bool = False,
    ) -> None:
        changed = application_name != self.current_app_name
        self.current_app_name = application_name
        if changed or force:
            self.active_app_changed.emit(application_name or "DEFAULT")


def _normalize_executable(executable: object) -> str | None:
    if not isinstance(executable, str):
        return None
    value = executable.strip().strip('"')
    if not value or value.upper() == "DEFAULT":
        return None
    return PureWindowsPath(value).name.upper()


def _belongs_to_root(hwnd: int, expected_root: int) -> bool:
    if hwnd == expected_root:
        return True
    try:
        root = int(_USER32.GetAncestor(wintypes.HWND(hwnd), GA_ROOT) or 0)
    except BaseException:
        return False
    return root == expected_root
