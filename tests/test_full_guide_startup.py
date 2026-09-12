"""A separate QApplication is required to exercise real startup wiring."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class FullGuideStartupTests(unittest.TestCase):
    def test_startup_query_toggle_and_conflict_do_not_write_user_data(self):
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).with_name("full_guide_startup_probe.py"))],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FULL_GUIDE_STARTUP_NO_USER_WRITES_OK", result.stdout)
