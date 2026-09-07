import unittest

from scripts.application_descriptor import ApplicationDescriptorFactory, ApplicationMetadata
from scripts.current_application_candidate import CurrentApplicationCandidateTracker
from scripts.shell_identity import WINDOWS_DESKTOP


class CurrentApplicationCandidateTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hwnd = 100
        self.process_ids = {100: 2000, 101: 999, 102: 3000}
        self.tracker = CurrentApplicationCandidateTracker(
            lambda: self.hwnd,
            process_id_provider=lambda hwnd: self.process_ids.get(hwnd),
            own_process_id=999,
        )

    def test_external_application_becomes_candidate(self) -> None:
        self.tracker.on_active_app_changed("code.exe")

        self.assertEqual(self.tracker.current_candidate, "CODE.EXE")
        self.assertEqual(self.tracker.editable_candidate(), "CODE.EXE")

    def test_self_window_does_not_replace_last_external_candidate(self) -> None:
        self.tracker.on_active_app_changed("CODE.EXE")
        self.hwnd = 101
        self.tracker.on_active_app_changed("python.exe")

        self.assertEqual(self.tracker.current_candidate, "CODE.EXE")

    def test_final_wps_logical_identity_is_preserved(self) -> None:
        self.tracker.on_active_app_changed("WPS_PDF")

        self.assertEqual(self.tracker.editable_candidate(), "WPS_PDF")

    def test_non_external_identity_does_not_replace_last_external_candidate(self) -> None:
        self.tracker.on_active_app_changed("CODE.EXE")
        for identity in ("DEFAULT", "GLOBAL", "WINDOWS_SHELL", "WPS_UNKNOWN"):
            with self.subTest(identity=identity):
                self.tracker.on_active_app_changed(identity)
                self.assertEqual(self.tracker.current_candidate, "CODE.EXE")
                self.assertEqual(self.tracker.editable_candidate(), "CODE.EXE")

    def test_desktop_is_actual_context_without_replacing_last_external_candidate(self) -> None:
        self.tracker.on_active_app_changed("CODE.EXE")
        self.tracker.on_active_app_changed(WINDOWS_DESKTOP)

        self.assertEqual(self.tracker.actual_context.runtime_identity, WINDOWS_DESKTOP)
        self.assertEqual(self.tracker.center_context.runtime_identity, WINDOWS_DESKTOP)
        self.assertEqual(self.tracker.last_external_descriptor.runtime_identity, "CODE.EXE")
        self.assertEqual(self.tracker.editable_candidate(), "CODE.EXE")

    def test_duplicate_foreground_context_does_not_emit_again(self) -> None:
        observed: list[object] = []
        self.tracker.foreground_context_changed.connect(observed.append)

        self.tracker.on_active_app_changed("CODE.EXE")
        self.tracker.on_active_app_changed("CODE.EXE")

        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0].runtime_identity, "CODE.EXE")

    def test_latest_external_application_replaces_previous_candidate(self) -> None:
        self.tracker.on_active_app_changed("CODE.EXE")
        self.hwnd = 102
        self.tracker.on_active_app_changed(
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )

        self.assertEqual(self.tracker.current_candidate, "CHROME.EXE")

    def test_unknown_hwnd_owner_does_not_replace_candidate(self) -> None:
        self.tracker.on_active_app_changed("CODE.EXE")
        self.hwnd = 404
        self.tracker.on_active_app_changed("OTHER.EXE")

        self.assertEqual(self.tracker.current_candidate, "CODE.EXE")
        self.assertEqual(self.tracker.actual_context.runtime_identity, "CODE.EXE")
        self.assertEqual(self.tracker.center_context.runtime_identity, "CODE.EXE")

    def test_unknown_external_application_is_retained_with_friendly_metadata(self) -> None:
        tracker = CurrentApplicationCandidateTracker(
            lambda: self.hwnd,
            process_id_provider=lambda hwnd: self.process_ids.get(hwnd),
            own_process_id=999,
            executable_path_provider=lambda: r"C:\Apps\typora.exe",
            descriptor_factory=ApplicationDescriptorFactory(
                lambda _path: ApplicationMetadata(product_name="Typora")
            ),
        )
        tracker.on_active_app_changed("typora.exe")

        self.assertEqual(tracker.current_descriptor.display_name, "Typora")
        self.assertFalse(tracker.current_descriptor.supported)

    def test_recent_descriptors_deduplicate_identities(self) -> None:
        self.tracker.on_active_app_changed("CODE.EXE")
        self.hwnd = 102
        self.tracker.on_active_app_changed("CHROME.EXE")
        self.hwnd = 100
        self.tracker.on_active_app_changed("CODE.EXE")

        self.assertEqual(
            [item.runtime_identity for item in self.tracker.recent_descriptors],
            ["CODE.EXE", "CHROME.EXE"],
        )


if __name__ == "__main__":
    unittest.main()
