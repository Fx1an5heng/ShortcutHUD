from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.shortcut_resolver import resolve_shortcuts
from scripts.wps_identity import (
    WPS_PDF,
    WPS_PRESENTATION,
    WPS_UNKNOWN,
    WPS_WRITER,
)


class WpsIdentityDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config_path = Path(__file__).parents[1] / "config" / "shortcuts.json"
        cls.data = json.loads(config_path.read_text(encoding="utf-8"))

    def test_unknown_profile_is_known_and_empty_for_global_only_resolution(self) -> None:
        self.assertIn(WPS_UNKNOWN, self.data)
        self.assertEqual(self.data[WPS_UNKNOWN], {})

    def test_pdf_profile_contains_only_the_officially_confirmed_pack(self) -> None:
        self.assertEqual(
            list(self.data[WPS_PDF]["Ctrl"]),
            ["F", "F2", "-", "0", "1", "2"],
        )
        self.assertEqual(list(self.data[WPS_PDF]["Alt+Shift"]), ["1"])

    def test_pdf_resolution_uses_app_source(self) -> None:
        entries = resolve_shortcuts(self.data, WPS_PDF, "Ctrl")
        self.assertEqual(
            [entry.key for entry in entries],
            ["F", "F2", "-", "0", "1", "2"],
        )
        self.assertTrue(all(entry.source == "APP" for entry in entries))

    def _assert_app_pack(
        self,
        application: str,
        modifier: str,
        expected_keys: list[str],
    ) -> None:
        entries = resolve_shortcuts(self.data, application, modifier)
        app_entries = [entry for entry in entries if entry.source == "APP"]
        self.assertEqual([entry.key for entry in app_entries], expected_keys)
        self.assertTrue(app_entries, f"{application}.{modifier}")

    def test_writer_profile_resolves_selected_packs_in_order(self) -> None:
        self.assertIn(WPS_WRITER, self.data)
        self._assert_app_pack(
            WPS_WRITER,
            "Ctrl",
            ["B", "I", "U", "H", "K", "Enter", "G", "D"],
        )
        self._assert_app_pack(
            WPS_WRITER,
            "Ctrl+Shift",
            ["E", "G", ",", ".", "=", "Tab"],
        )

    def test_presentation_profile_resolves_selected_packs_in_order(self) -> None:
        self.assertIn(WPS_PRESENTATION, self.data)
        self._assert_app_pack(
            WPS_PRESENTATION,
            "Ctrl",
            ["G", "K", "Tab", "+", "-", "0", "H", "F"],
        )
        self._assert_app_pack(
            WPS_PRESENTATION,
            "Ctrl+Shift",
            ["G", "Tab", ",", ".", "="],
        )
        self._assert_app_pack(WPS_PRESENTATION, "Shift", ["F5"])

    def test_pdf_alt_shift_resolution_uses_app_source(self) -> None:
        self._assert_app_pack(WPS_PDF, "Alt+Shift", ["1"])

    def test_logical_profiles_have_no_no_modifier_group(self) -> None:
        for application in (WPS_WRITER, WPS_PDF, WPS_PRESENTATION):
            with self.subTest(application=application):
                self.assertNotIn("NoModifier", self.data[application])

    def test_logical_profiles_contain_no_screenshot_shortcuts(self) -> None:
        forbidden_terms = (
            "screenshot",
            "screen grab",
            "screengrab",
            "截图",
            "prtsc",
            "printscreen",
        )
        for application in (WPS_WRITER, WPS_PDF, WPS_PRESENTATION):
            for modifier, shortcuts in self.data[application].items():
                for key, description in shortcuts.items():
                    location = f"{application}.{modifier}.{key}"
                    shortcut_text = json.dumps(
                        {"key": key, "description": description},
                        ensure_ascii=False,
                    ).casefold()
                    for forbidden in forbidden_terms:
                        self.assertNotIn(
                            forbidden.casefold(),
                            shortcut_text,
                            location,
                        )

    def test_logical_profiles_do_not_cross_resolve(self) -> None:
        expected_ctrl_keys = {
            WPS_WRITER: ["B", "I", "U", "H", "K", "Enter", "G", "D"],
            WPS_PDF: ["F", "F2", "-", "0", "1", "2"],
            WPS_PRESENTATION: ["G", "K", "Tab", "+", "-", "0", "H", "F"],
        }
        for application, expected_keys in expected_ctrl_keys.items():
            with self.subTest(application=application):
                entries = resolve_shortcuts(self.data, application, "Ctrl")
                self.assertEqual([entry.key for entry in entries], expected_keys)
                self.assertTrue(all(entry.source == "APP" for entry in entries))


if __name__ == "__main__":
    unittest.main()
