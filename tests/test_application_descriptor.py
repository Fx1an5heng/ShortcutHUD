import unittest

from scripts.application_descriptor import (
    ApplicationDescriptorFactory,
    ApplicationMetadata,
)
from scripts.shell_identity import WINDOWS_DESKTOP


class ApplicationDescriptorTests(unittest.TestCase):
    def test_unknown_foreground_application_still_has_a_descriptor(self) -> None:
        descriptor = ApplicationDescriptorFactory(
            lambda _path: ApplicationMetadata()
        ).describe("typora.exe")

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.runtime_identity, "TYPORA.EXE")
        self.assertEqual(descriptor.display_name, "Typora")
        self.assertFalse(descriptor.supported)

    def test_version_metadata_is_preferred_for_an_unsupported_app(self) -> None:
        descriptor = ApplicationDescriptorFactory(
            lambda _path: {"ProductName": "Notepad++", "FileDescription": "Text Editor"}
        ).describe("notepad++.exe", r"C:\Apps\notepad++.exe")

        self.assertEqual(descriptor.display_name, "Notepad++")
        self.assertEqual(descriptor.executable_path, r"C:\Apps\notepad++.exe")

    def test_metadata_failure_falls_back_to_executable_stem(self) -> None:
        def failing_provider(_path: str):
            raise OSError("unavailable")

        descriptor = ApplicationDescriptorFactory(failing_provider).describe("my_tool.exe")

        self.assertEqual(descriptor.display_name, "My Tool")

    def test_desktop_has_a_first_class_context_descriptor(self) -> None:
        descriptor = ApplicationDescriptorFactory().describe(WINDOWS_DESKTOP)

        self.assertEqual(descriptor.display_name, "Windows Desktop")
        self.assertEqual(descriptor.context_kind, "desktop")
        self.assertFalse(descriptor.supported)


if __name__ == "__main__":
    unittest.main()
