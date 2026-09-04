import unittest

import win32gui

from scripts.fullscreen_detection import (
    FullscreenWindowSnapshot,
    Rect,
    WindowsFullscreenDetector,
    is_monitor_covering_window,
)


class FullscreenDetectionTests(unittest.TestCase):
    def test_production_detector_rejects_desktop_handle(self) -> None:
        detector = WindowsFullscreenDetector()

        self.assertFalse(detector.is_fullscreen(win32gui.GetDesktopWindow()))

    def test_monitor_sized_window_is_fullscreen(self) -> None:
        bounds = Rect(0, 0, 1920, 1080)

        self.assertTrue(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(bounds, bounds)
            )
        )

    def test_two_pixel_frame_difference_is_tolerated(self) -> None:
        self.assertTrue(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(
                    Rect(-2, -2, 1922, 1082),
                    Rect(0, 0, 1920, 1080),
                )
            )
        )

    def test_work_area_sized_maximized_window_is_not_fullscreen(self) -> None:
        self.assertFalse(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(
                    Rect(0, 0, 1920, 1040),
                    Rect(0, 0, 1920, 1080),
                    Rect(0, 0, 1920, 1040),
                )
            )
        )

    def test_near_monitor_work_area_prefers_the_closer_boundary(self) -> None:
        monitor = Rect(0, 0, 1920, 1080)
        auto_hide_work_area = Rect(0, 0, 1920, 1078)

        self.assertFalse(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(
                    auto_hide_work_area,
                    monitor,
                    auto_hide_work_area,
                )
            )
        )
        self.assertTrue(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(
                    monitor,
                    monitor,
                    auto_hide_work_area,
                )
            )
        )

    def test_hidden_minimized_or_cloaked_window_is_not_fullscreen(self) -> None:
        bounds = Rect(0, 0, 1920, 1080)

        for field in ("visible", "minimized", "cloaked"):
            with self.subTest(field=field):
                values = {"visible": True, "minimized": False, "cloaked": False}
                values[field] = field != "visible"
                self.assertFalse(
                    is_monitor_covering_window(
                        FullscreenWindowSnapshot(bounds, bounds, **values)
                    )
                )

    def test_shell_or_own_process_window_is_not_fullscreen(self) -> None:
        bounds = Rect(0, 0, 1920, 1080)

        self.assertFalse(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(bounds, bounds, shell_surface=True)
            )
        )
        self.assertFalse(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(bounds, bounds, own_process=True)
            )
        )

    def test_second_monitor_uses_its_virtual_screen_bounds(self) -> None:
        second_monitor = Rect(1920, -160, 4480, 1280)

        self.assertTrue(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(second_monitor, second_monitor)
            )
        )
        self.assertFalse(
            is_monitor_covering_window(
                FullscreenWindowSnapshot(
                    second_monitor,
                    Rect(0, 0, 1920, 1080),
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
