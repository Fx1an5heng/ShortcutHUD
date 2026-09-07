import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from import_powertoys_shortcuts import ManifestImportError, convert_manifest


def _manifest():
    return {"PackageName": "Example.App", "Name": "Example", "WindowFilter": "example.exe", "BackgroundProcess": False, "Shortcuts": [{"SectionName": "General", "Properties": [{"Name": "Open File", "Recommended": True, "Shortcut": [{"Win": False, "Ctrl": True, "Shift": False, "Alt": False, "Keys": ["O"]}]}, {"Name": "Refresh", "Shortcut": [{"Win": False, "Ctrl": False, "Shift": False, "Alt": False, "Keys": ["F5"]}]}, {"Name": "Chord", "Shortcut": [{"Win": False, "Ctrl": True, "Shift": False, "Alt": False, "Keys": ["K"]}, {"Win": False, "Ctrl": True, "Shift": False, "Alt": False, "Keys": ["S"]}]}]}]}


class PowerToysImporterTests(unittest.TestCase):
    def _convert(self, document=None):
        return convert_manifest(document or _manifest(), pack_id="example.windows", product={"en": "Example", "zh_CN": "示例"}, app_identities=["EXAMPLE.EXE"], aliases=[], official_reference_title="Official", official_reference_url="https://example.test/docs", upstream_revision="abc123", translation_map={"General": "常规", "Open File": "打开文件", "Chord": "组合键"})

    def test_valid_manifest_is_deterministic_and_maps_core_fields(self):
        first = self._convert(); second = self._convert()
        self.assertEqual(first, second)
        self.assertEqual(first.pack["entries"][0]["trigger"], {"kind": "combo", "keys": ["Ctrl", "O"]})
        self.assertTrue(first.pack["entries"][0]["recommended"])
        self.assertEqual(first.pack["entries"][1]["trigger"], {"kind": "single", "keys": ["F5"]})
        self.assertEqual(first.pack["entries"][2]["trigger"]["kind"], "sequence")
        self.assertEqual(first.unsupported, ())
        self.assertEqual(len(first.catalog_only), 2)
        self.assertEqual(first.upstream_entries, 3)
        self.assertEqual(first.pack["entries"][0]["category"], "general")

    def test_range_family_remains_unsupported_without_guessing_an_expansion(self):
        document = _manifest(); document["Shortcuts"][0]["Properties"][0]["Shortcut"][0]["Keys"] = ["<Arrow>"]
        result = self._convert(document)
        self.assertEqual([entry["id"] for entry in result.pack["entries"]], ["example.refresh", "example.chord"])
        self.assertIn("unsupported key representation", result.unsupported[0])
        self.assertNotIn("Arrow", result.pack["entries"])

    def test_background_manifest_fails_safely(self):
        document = _manifest(); document["BackgroundProcess"] = True
        with self.assertRaises(ManifestImportError): self._convert(document)


if __name__ == "__main__": unittest.main()
