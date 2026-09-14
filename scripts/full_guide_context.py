"""Capture the external app and its monitor before a Guide can take focus."""
from __future__ import annotations

from dataclasses import dataclass
import os

import win32api
import win32process
from PySide6.QtCore import QRect
from PySide6.QtGui import QCursor, QGuiApplication

from .application_descriptor import ApplicationDescriptor, ApplicationDescriptorFactory
from .catalog_application_registry import CatalogApplicationRegistry
from .shell_identity import WINDOWS_DESKTOP


@dataclass(frozen=True, slots=True)
class GuideSnapshot:
    descriptor: ApplicationDescriptor
    hwnd: int
    monitor_name: str
    available_geometry: tuple[int, int, int, int]


def choose_monitor(screens, device: str | None, cursor: tuple[int, int]):
    """Native device names select Qt logical geometry, including mixed DPI."""
    return next((screen for screen in screens if device and screen[0].casefold() == device.casefold()), None) or next((screen for screen in screens if QRect(*screen[1]).contains(*cursor)), None) or (screens[0] if screens else ("", (0, 0, 1024, 768)))


def guide_geometry(available: tuple[int, int, int, int]) -> QRect:
    """Cover one monitor without entering exclusive display mode."""
    x, y, width, height = available
    return QRect(x, y, max(1, width), max(1, height))


class WindowsGuideContext:
    def __init__(self, monitor, identity_runtime, tracker, catalog_provider, profiles_provider, language_provider) -> None:
        self.monitor, self.identity_runtime, self.tracker = monitor, identity_runtime, tracker
        self.catalog_provider, self.profiles_provider, self.language_provider = catalog_provider, profiles_provider, language_provider
        self.factory = ApplicationDescriptorFactory()

    def capture(self) -> GuideSnapshot:
        # Poll synchronously. A 1-second foreground cache is not sufficient for
        # an explicit command immediately after Alt+Tab.
        self.monitor.check_foreground_app()
        hwnd = int(self.monitor.current_hwnd or 0)
        try:
            own = bool(hwnd and win32process.GetWindowThreadProcessId(hwnd)[1] == os.getpid())
        except Exception:
            own = False
        if own:
            descriptor = self.tracker.center_context
        else:
            identity = self.identity_runtime.current_app_name
            descriptor = self.factory.describe(identity, self.monitor.current_executable_path)
        if descriptor is None:
            descriptor = self.factory.describe(WINDOWS_DESKTOP)
        registry = CatalogApplicationRegistry(self.catalog_provider(), self.profiles_provider(), self.language_provider())
        descriptor = registry.describe(descriptor)
        record = registry.find_by_identity(descriptor.runtime_identity)
        if record is not None and not descriptor.supported:
            # USER-only display overrides are Registry data as well.
            from dataclasses import replace
            descriptor = replace(descriptor, display_name=record.display_name)
        device = None
        if hwnd and not own and descriptor.context_kind != "desktop":
            try:
                device = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd, 2))["Device"]
            except Exception:
                pass
        screens = [(screen.name(), screen.geometry().getRect()) for screen in QGuiApplication.screens()]
        cursor = QCursor.pos()
        name, geometry = choose_monitor(screens, device, (cursor.x(), cursor.y()))
        return GuideSnapshot(descriptor, hwnd if not own else 0, name, tuple(geometry))
