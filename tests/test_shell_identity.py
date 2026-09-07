import unittest

from scripts.shell_identity import (
    EXPLORER_EXECUTABLE,
    WINDOWS_DESKTOP,
    WINDOWS_SHELL,
    classify_shell_application,
)


class ShellIdentityTests(unittest.TestCase):
    def test_file_explorer_window_classes_keep_explorer_identity(self) -> None:
        for window_class in ("CabinetWClass", "ExploreWClass"):
            with self.subTest(window_class=window_class):
                self.assertEqual(
                    classify_shell_application(
                        r"C:\Windows\explorer.exe",
                        101,
                        lambda _hwnd, value=window_class: value,
                    ),
                    EXPLORER_EXECUTABLE,
                )

    def test_desktop_classes_have_a_distinct_desktop_identity(self) -> None:
        for window_class in ("Progman", "WorkerW"):
            with self.subTest(window_class=window_class):
                self.assertEqual(
                    classify_shell_application(
                        "EXPLORER.EXE",
                        202,
                        lambda _hwnd, value=window_class: value,
                    ),
                    WINDOWS_DESKTOP,
                )

    def test_taskbar_classes_remain_non_desktop_shell_contexts(self) -> None:
        for window_class in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            with self.subTest(window_class=window_class):
                self.assertEqual(
                    classify_shell_application(
                        "EXPLORER.EXE", 202,
                        lambda _hwnd, value=window_class: value,
                    ),
                    WINDOWS_SHELL,
                )

    def test_unknown_or_unreadable_explorer_class_fails_closed(self) -> None:
        self.assertEqual(
            classify_shell_application(
                "explorer.exe",
                303,
                lambda _hwnd: "UnexpectedExplorerSurface",
            ),
            WINDOWS_SHELL,
        )

        def fail_to_read(_hwnd: int) -> str:
            raise OSError("class lookup failed")

        self.assertEqual(
            classify_shell_application("explorer.exe", 404, fail_to_read),
            WINDOWS_SHELL,
        )

    def test_non_explorer_application_passes_through_without_class_read(self) -> None:
        reads: list[int] = []

        self.assertEqual(
            classify_shell_application(
                r"C:\Program Files\Microsoft VS Code\Code.exe",
                505,
                lambda hwnd: reads.append(hwnd) or "Ignored",
            ),
            "CODE.EXE",
        )
        self.assertEqual(reads, [])


if __name__ == "__main__":
    unittest.main()
