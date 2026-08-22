from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.shortcut_resolver import resolve_shortcuts
from scripts.wps_identity import WPS_PDF, WPS_UNKNOWN


class WpsIdentityDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config_path = Path(__file__).parents[1] / "config" / "shortcuts.json"
        cls.data = json.loads(config_path.read_text(encoding="utf-8"))

    def test_unknown_profile_is_known_and_empty_for_global_only_resolution(self) -> None:
        self.assertIn(WPS_UNKNOWN, self.data)
        self.assertEqual(self.data[WPS_UNKNOWN], {})

    def test_pdf_profile_contains_only_the_previously_selected_minimal_pack(self) -> None:
        self.assertEqual(
            list(self.data[WPS_PDF]["Ctrl"]),
            ["F", "F2", "DOWN", "-", "0", "1", "2"],
        )
        self.assertEqual(list(self.data[WPS_PDF]["Alt+Shift"]), ["1"])

    def test_pdf_resolution_uses_app_source(self) -> None:
        entries = resolve_shortcuts(self.data, WPS_PDF, "Ctrl")
        self.assertEqual(
            [entry.key for entry in entries[:7]],
            ["F", "F2", "DOWN", "-", "0", "1", "2"],
        )
        self.assertTrue(all(entry.source == "APP" for entry in entries[:7]))


if __name__ == "__main__":
    unittest.main()
