from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from scripts.application_identity import (
    EVENT_OBJECT_FOCUS,
    ApplicationIdentityRuntime,
)
from scripts.foreground_monitor import ForegroundMonitor
from scripts.shell_identity import EXPLORER_EXECUTABLE, WINDOWS_SHELL
from scripts.shortcut_resolver import resolve_shortcuts
from scripts.wps_identity import (
    HIGH_CONFIDENCE,
    UNKNOWN_CONFIDENCE,
    WPS_PDF,
    WPS_PRESENTATION,
    WPS_UNKNOWN,
    WPS_WRITER,
    WpsIdentityResult,
)


class _FakeMonitor:
    def __init__(self) -> None:
        self.current_hwnd = 0
        self.current_app_name: str | None = None
        self.check_count = 0

    def check_foreground_app(self) -> bool:
        self.check_count += 1
        return False


class _FakeWorker:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls
        self.requests = []

    def start(self) -> None:
        self.calls.append("worker.start")

    def submit(self, request: object) -> bool:
        self.requests.append(request)
        self.calls.append(("worker.submit", request))
        return True

    def invalidate(self, generation: int) -> None:
        self.calls.append(("worker.invalidate", generation))

    def stop_accepting_requests(self) -> None:
        self.calls.append("worker.stop_accepting")

    def stop(self, timeout: float = 1.0) -> bool:
        self.calls.append(("worker.stop", timeout))
        return True


class _FakeHook:
    def __init__(self, _callback: object, calls: list[object]) -> None:
        self.calls = calls
        self.last_error = None

    def start(self) -> bool:
        self.calls.append("hook.start")
        return True

    def stop(self) -> None:
        self.calls.append("hook.stop")


def _result(
    hwnd: int,
    generation: int,
    logical_app_id: str,
    confidence: str = HIGH_CONFIDENCE,
) -> WpsIdentityResult:
    now = time.monotonic()
    return WpsIdentityResult(
        hwnd=hwnd,
        generation=generation,
        logical_app_id=logical_app_id,
        confidence=confidence,
        evidence=(logical_app_id,),
        requested_at=now,
        resolved_at=now,
        duration_ms=1.0,
    )


class ApplicationIdentityRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.calls: list[object] = []
        self.monitor = _FakeMonitor()
        self.worker = _FakeWorker(self.calls)
        self.runtime = ApplicationIdentityRuntime(
            self.monitor,
            worker=self.worker,
            event_hook_factory=lambda callback: _FakeHook(
                callback,
                self.calls,
            ),
        )

    def test_ordinary_application_bypasses_wps_worker(self) -> None:
        self.runtime.on_foreground_changed(
            45,
            r"C:\Program Files\Microsoft VS Code\Code.exe",
        )
        self.assertEqual(self.runtime.current_app_name, "CODE.EXE")
        self.assertEqual(self.runtime.current_logical_app_id, "CODE.EXE")
        self.assertEqual(self.worker.requests, [])

    def test_explorer_identity_is_reclassified_for_every_hwnd(self) -> None:
        window_classes = {
            101: "CabinetWClass",
            202: "Progman",
            303: "Shell_TrayWnd",
            404: "ExploreWClass",
        }
        class_reads: list[int] = []

        def read_window_class(hwnd: int) -> str:
            class_reads.append(hwnd)
            return window_classes[hwnd]

        runtime = ApplicationIdentityRuntime(
            self.monitor,
            worker=self.worker,
            event_hook_factory=lambda callback: _FakeHook(
                callback,
                self.calls,
            ),
            window_class_provider=read_window_class,
        )
        observed: list[str | None] = []
        for hwnd in (101, 202, 303, 404):
            runtime.on_foreground_changed(hwnd, "explorer.exe")
            observed.append(runtime.current_logical_app_id)

        self.assertEqual(
            observed,
            [
                EXPLORER_EXECUTABLE,
                WINDOWS_SHELL,
                WINDOWS_SHELL,
                EXPLORER_EXECUTABLE,
            ],
        )
        self.assertEqual(class_reads, [101, 202, 303, 404])
        self.assertEqual(self.worker.requests, [])

    def test_wps_pending_fails_closed_to_global_only_profile(self) -> None:
        self.runtime.on_foreground_changed(123, "wps.exe")
        self.assertTrue(self.runtime.identity_pending)
        self.assertEqual(self.runtime.current_app_name, WPS_UNKNOWN)

        data = {
            WPS_UNKNOWN: {},
            "DEFAULT": {"Ctrl": {"D": "Default"}},
            "GLOBAL": {"Ctrl": {"G": "Global"}},
        }
        entries = resolve_shortcuts(data, self.runtime.current_app_name, "Ctrl")
        self.assertEqual([(entry.key, entry.source) for entry in entries], [("G", "GLOBAL")])

    def test_current_high_result_publishes_shortcut_profile(self) -> None:
        self.runtime.on_foreground_changed(123, "WPS.EXE")
        generation = self.worker.requests[-1].generation
        self.runtime._on_worker_result(_result(123, generation, WPS_WRITER))
        self.assertFalse(self.runtime.identity_pending)
        self.assertEqual(self.runtime.current_logical_app_id, WPS_WRITER)
        self.assertEqual(self.runtime.current_app_name, WPS_WRITER)

    def test_presentation_result_publishes_logical_shortcut_profile(self) -> None:
        self.runtime.on_foreground_changed(123, "WPS.EXE")
        generation = self.worker.requests[-1].generation
        self.runtime._on_worker_result(
            _result(123, generation, WPS_PRESENTATION)
        )
        self.assertEqual(
            self.runtime.current_logical_app_id,
            WPS_PRESENTATION,
        )
        self.assertEqual(self.runtime.current_app_name, WPS_PRESENTATION)

    def test_stale_result_cannot_override_newer_same_hwnd_request(self) -> None:
        self.runtime.on_foreground_changed(123, "WPS.EXE")
        old_generation = self.worker.requests[-1].generation
        self.runtime.on_foreground_changed(123, "WPS.EXE")
        new_generation = self.worker.requests[-1].generation

        self.runtime._on_worker_result(_result(123, old_generation, WPS_PDF))
        self.assertEqual(self.runtime.current_app_name, WPS_UNKNOWN)
        self.runtime._on_worker_result(_result(123, new_generation, WPS_WRITER))
        self.assertEqual(self.runtime.current_app_name, WPS_WRITER)

    def test_same_hwnd_can_publish_writer_then_pdf(self) -> None:
        self.runtime.on_foreground_changed(123, "WPS.EXE")
        first_generation = self.worker.requests[-1].generation
        self.runtime._on_worker_result(_result(123, first_generation, WPS_WRITER))

        self.runtime.on_foreground_changed(123, "WPS.EXE")
        second_generation = self.worker.requests[-1].generation
        self.runtime._on_worker_result(_result(123, second_generation, WPS_PDF))

        self.assertGreater(second_generation, first_generation)
        self.assertEqual(self.runtime.current_logical_app_id, WPS_PDF)
        self.assertEqual(self.runtime.current_app_name, WPS_PDF)

    def test_unknown_or_failed_result_remains_fail_closed(self) -> None:
        self.runtime.on_foreground_changed(123, "WPS.EXE")
        generation = self.worker.requests[-1].generation
        self.runtime._on_worker_result(
            _result(123, generation, WPS_UNKNOWN, UNKNOWN_CONFIDENCE)
        )
        self.assertFalse(self.runtime.identity_pending)
        self.assertEqual(self.runtime.current_app_name, WPS_UNKNOWN)

    def test_focus_event_same_hwnd_creates_new_generation_without_blocking(self) -> None:
        self.monitor.current_hwnd = 123
        self.monitor.current_app_name = "WPS.EXE"
        self.runtime.on_foreground_changed(123, "WPS.EXE")
        previous_generation = self.worker.requests[-1].generation

        started = time.perf_counter()
        self.runtime._on_windows_event(EVENT_OBJECT_FOCUS, 0, 0, 0)
        elapsed_ms = (time.perf_counter() - started) * 1000

        self.assertLess(elapsed_ms, 20)
        self.assertGreater(self.worker.requests[-1].generation, previous_generation)

    def test_shutdown_order_stops_requests_hook_then_worker(self) -> None:
        self.runtime.stop()
        self.assertEqual(
            [call for call in self.calls if isinstance(call, str)],
            ["worker.stop_accepting", "hook.stop"],
        )
        stop_accepting_index = self.calls.index("worker.stop_accepting")
        hook_index = self.calls.index("hook.stop")
        worker_stop_index = next(
            index
            for index, call in enumerate(self.calls)
            if isinstance(call, tuple) and call[0] == "worker.stop"
        )
        self.assertLess(stop_accepting_index, hook_index)
        self.assertLess(hook_index, worker_stop_index)


class ForegroundMonitorSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_raw_signal_tracks_hwnd_change_even_when_exe_is_same(self) -> None:
        monitor = ForegroundMonitor(interval_ms=60_000)
        monitor.stop_monitoring()
        snapshots = []
        app_changes = []
        monitor.foreground_changed.connect(
            lambda hwnd, exe: snapshots.append((hwnd, exe))
        )
        monitor.active_app_changed.connect(app_changes.append)

        with patch(
            "scripts.foreground_monitor.win32gui.GetForegroundWindow",
            side_effect=[101, 202],
        ), patch.object(monitor, "get_exe_from_hwnd", return_value="Code.exe"):
            self.assertTrue(monitor.check_foreground_app())
            self.assertTrue(monitor.check_foreground_app())

        self.assertEqual(snapshots, [(101, "Code.exe"), (202, "Code.exe")])
        self.assertEqual(app_changes, ["Code.exe"])

    def test_polled_signal_emits_when_hwnd_and_exe_are_unchanged(self) -> None:
        monitor = ForegroundMonitor(interval_ms=60_000)
        monitor.stop_monitoring()
        transitions = []
        polls = []
        monitor.foreground_changed.connect(
            lambda hwnd, exe: transitions.append((hwnd, exe))
        )
        monitor.foreground_polled.connect(
            lambda hwnd, exe: polls.append((hwnd, exe))
        )

        with patch(
            "scripts.foreground_monitor.win32gui.GetForegroundWindow",
            return_value=101,
        ), patch.object(monitor, "get_exe_from_hwnd", return_value="Code.exe"):
            self.assertTrue(monitor.check_foreground_app())
            self.assertFalse(monitor.check_foreground_app())

        self.assertEqual(transitions, [(101, "Code.exe")])
        self.assertEqual(polls, [(101, "Code.exe"), (101, "Code.exe")])


if __name__ == "__main__":
    unittest.main()
