"""Windows foreground-window fullscreen detection with pure geometry seams."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

import win32api
import win32con
import win32gui
import win32process


DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14
MONITOR_DEFAULTTONEAREST = 2
DEFAULT_EDGE_TOLERANCE_PX = 2


@dataclass(frozen=True, slots=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def has_area(self) -> bool:
        return self.right > self.left and self.bottom > self.top


@dataclass(frozen=True, slots=True)
class FullscreenWindowSnapshot:
    """All state needed for a deterministic fullscreen decision."""

    window_bounds: Rect
    monitor_bounds: Rect
    work_area_bounds: Rect | None = None
    visible: bool = True
    minimized: bool = False
    cloaked: bool = False
    shell_surface: bool = False
    own_process: bool = False


def is_monitor_covering_window(
    snapshot: FullscreenWindowSnapshot,
    *,
    edge_tolerance_px: int = DEFAULT_EDGE_TOLERANCE_PX,
) -> bool:
    """Return whether one eligible window covers its actual monitor bounds."""

    if (
        not snapshot.visible
        or snapshot.minimized
        or snapshot.cloaked
        or snapshot.shell_surface
        or snapshot.own_process
        or not snapshot.window_bounds.has_area
        or not snapshot.monitor_bounds.has_area
    ):
        return False

    tolerance = max(0, int(edge_tolerance_px))
    window = snapshot.window_bounds
    monitor = snapshot.monitor_bounds
    monitor_delta = _edge_delta(window, monitor)
    work_area = snapshot.work_area_bounds
    if (
        work_area is not None
        and work_area != monitor
        and _edge_delta(window, work_area) < monitor_delta
    ):
        return False
    return monitor_delta <= tolerance


class WindowsFullscreenDetector:
    """Read one HWND's physical DWM bounds and compare its own monitor."""

    def __init__(
        self,
        *,
        own_process_id: int | None = None,
        edge_tolerance_px: int = DEFAULT_EDGE_TOLERANCE_PX,
    ) -> None:
        self._own_process_id = int(own_process_id or os.getpid())
        self._edge_tolerance_px = max(0, int(edge_tolerance_px))

    def is_fullscreen(self, hwnd: object) -> bool:
        try:
            normalized_hwnd = int(hwnd or 0)
            snapshot = self._read_snapshot(normalized_hwnd)
        except BaseException:
            return False
        if snapshot is None:
            return False
        return is_monitor_covering_window(
            snapshot,
            edge_tolerance_px=self._edge_tolerance_px,
        )

    def _read_snapshot(self, hwnd: int) -> FullscreenWindowSnapshot | None:
        if hwnd <= 0 or not win32gui.IsWindow(hwnd):
            return None

        shell_handles = {
            int(win32gui.GetShellWindow() or 0),
            int(win32gui.GetDesktopWindow() or 0),
        }
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        window_bounds = _dwm_window_bounds(hwnd)
        if window_bounds is None:
            return None

        monitor = win32api.MonitorFromWindow(
            hwnd,
            getattr(win32con, "MONITOR_DEFAULTTONEAREST", MONITOR_DEFAULTTONEAREST),
        )
        monitor_info = win32api.GetMonitorInfo(monitor)
        monitor_bounds = _rect_from_sequence(monitor_info["Monitor"])
        work_area_bounds = _rect_from_sequence(monitor_info["Work"])

        return FullscreenWindowSnapshot(
            window_bounds=window_bounds,
            monitor_bounds=monitor_bounds,
            work_area_bounds=work_area_bounds,
            visible=bool(win32gui.IsWindowVisible(hwnd)),
            minimized=bool(win32gui.IsIconic(hwnd)),
            cloaked=_dwm_window_is_cloaked(hwnd),
            shell_surface=hwnd in shell_handles,
            own_process=int(process_id or 0) == self._own_process_id,
        )


def _rect_from_sequence(value: object) -> Rect:
    left, top, right, bottom = value  # type: ignore[misc]
    return Rect(int(left), int(top), int(right), int(bottom))


def _edge_delta(first: Rect, second: Rect) -> int:
    return max(
        abs(first.left - second.left),
        abs(first.top - second.top),
        abs(first.right - second.right),
        abs(first.bottom - second.bottom),
    )


def _dwm_window_bounds(hwnd: int) -> Rect | None:
    rect = wintypes.RECT()
    result = _dwm_get_window_attribute(
        hwnd,
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if result != 0:
        return None
    return Rect(rect.left, rect.top, rect.right, rect.bottom)


def _dwm_window_is_cloaked(hwnd: int) -> bool:
    cloaked = wintypes.DWORD()
    result = _dwm_get_window_attribute(
        hwnd,
        DWMWA_CLOAKED,
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return result == 0 and bool(cloaked.value)


_DWMAPI = ctypes.WinDLL("dwmapi", use_last_error=True)
_dwm_get_window_attribute = _DWMAPI.DwmGetWindowAttribute
_dwm_get_window_attribute.argtypes = (
    wintypes.HWND,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.DWORD,
)
_dwm_get_window_attribute.restype = ctypes.c_long
