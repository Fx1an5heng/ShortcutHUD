import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtWidgets import QApplication, QLabel

from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.shortcut_catalog import ShortcutCatalog, parse_shortcut_pack
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver
from scripts.shortcut_hud import ShortcutHudWindow
from scripts.shortcut_hud_controller import ShortcutHudController
from scripts.shortcut_library_dialog import ShortcutLibraryModel


_PACK_DIRECTORY = Path(__file__).resolve().parents[1] / "config" / "shortcut_packs"


class _Config:
    def __init__(self, catalog: ShortcutCatalog, language: str) -> None:
        self.catalog = catalog
        self.language = language

    def get_shortcut_catalog(self) -> ShortcutCatalog:
        return self.catalog

    def get_all_shortcuts(self) -> dict[str, object]:
        return {}

    def get_setting(self, key: str, default: object = None) -> object:
        return self.language if key == "language" else default


class _Foreground:
    identity_pending = False

    def __init__(self, application_name: str) -> None:
        self.current_app_name = application_name


class _Hud:
    def __init__(self) -> None:
        self.rendered: tuple[str, str, list[object], str | None, str | None] | None = None

    def isVisible(self) -> bool:
        return False

    def hide(self) -> None:
        pass

    def show_hud(self) -> None:
        pass

    def set_entries(self, application_name, modifier, entries, language, display_name=None) -> None:
        self.rendered = (application_name, modifier, entries, language, display_name)


class _Proxy:
    def current_physical_win_vk(self):
        return None

    def activate_for_current_hold(self, _win_vk):
        return False


class HudCatalogLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])
        cls.catalog = ShortcutCatalog.from_legacy_shortcuts({}).with_packs_from(_PACK_DIRECTORY)

    def _controller(self, language: str, application_name: str = "CODE.EXE"):
        hud = _Hud()
        controller = ShortcutHudController(
            _Config(self.catalog, language), _Foreground(application_name), hud, _Proxy()
        )
        controller._current_modifier = "Ctrl"
        return controller, hud

    def test_vscode_catalog_resolution_is_localized_once_for_hud_and_center(self) -> None:
        controller, hud = self._controller("zh_CN")
        try:
            entries = controller._resolve_current_entries()
            by_key = {entry.key: entry.description for entry in entries}
            self.assertEqual(by_key["P"], "按名称打开文件")
            self.assertEqual(by_key["Z"], "撤销上一次编辑")
            self.assertEqual(by_key["B"], "显示或隐藏主侧边栏")
            self.assertEqual(by_key["`"], "显示或隐藏集成终端")
            controller._render(entries)
            self.assertEqual(hud.rendered[4], "Visual Studio Code")
            self.assertNotEqual(hud.rendered[4], "CODE.EXE")

            with TemporaryDirectory() as directory:
                model = ShortcutLibraryModel(
                    self.catalog,
                    QuickHudSelectionStore(Path(directory) / "selection.json"),
                    language="zh_CN",
                )
                center = next(row for row in model.rows("CODE.EXE") if row.entry.id == "vscode.quick-open")
                self.assertEqual(center.description, by_key["P"])
        finally:
            controller.stop()

    def test_vscode_english_resolution_remains_english(self) -> None:
        controller, _hud = self._controller("en_US")
        try:
            self.assertEqual(
                {entry.key: entry.description for entry in controller._resolve_current_entries()}["P"],
                "Open a file by name",
            )
        finally:
            controller.stop()

    def test_missing_requested_catalog_locale_falls_back_to_english(self) -> None:
        document = json.loads((_PACK_DIRECTORY / "vscode.json").read_text(encoding="utf-8"))
        entry = next(item for item in document["entries"] if item["id"] == "vscode.quick-open")
        entry["description"] = {"en": "English fallback"}
        catalog = ShortcutCatalog(parse_shortcut_pack(document).entries)
        resolved = CatalogShortcutResolver(catalog).resolve("CODE.EXE", "Ctrl", language="zh_CN")
        self.assertEqual(next(item.description for item in resolved if item.key == "P"), "English fallback")

    def test_legacy_and_unsupported_application_name_fallbacks_remain_friendly(self) -> None:
        legacy = ShortcutCatalog.from_legacy_shortcuts(
            {"NOTEPAD.EXE": {"Ctrl": {"S": {"en": "Save", "zh": "保存"}}}}
        )
        controller = ShortcutHudController(_Config(legacy, "zh_CN"), _Foreground("NOTEPAD.EXE"), hud := _Hud(), _Proxy())
        controller._current_modifier = "Ctrl"
        try:
            entries = controller._resolve_current_entries()
            self.assertEqual(entries[0].description, "保存")
            controller._render(entries)
            self.assertEqual(hud.rendered[4], "Notepad")
        finally:
            controller.stop()

        fallback = ShortcutCatalog.from_legacy_shortcuts({"DEFAULT": {"Ctrl": {"C": "Copy"}}})
        controller = ShortcutHudController(_Config(fallback, "en_US"), _Foreground("UNKNOWN_THIRD_PARTY.EXE"), hud := _Hud(), _Proxy())
        controller._current_modifier = "Ctrl"
        try:
            controller._render(controller._resolve_current_entries())
            self.assertEqual(hud.rendered[4], "Unknown Third Party")
        finally:
            controller.stop()

    def test_catalog_selection_respects_compact_hud_eight_row_cap(self) -> None:
        eligible = [
            entry for entry in self.catalog.entries
            if entry.scope == "APP" and "CODE.EXE" in entry.application_ids
            and entry.trigger.is_quick_hud_eligible()
            and entry.trigger.runtime_modifier() == "Ctrl"
        ]
        self.assertGreaterEqual(len(eligible), 30)
        for selected_count in (8, 9, 30):
            with self.subTest(selected_count=selected_count), TemporaryDirectory() as directory:
                store = QuickHudSelectionStore(Path(directory) / "selection.json")
                store.set_selected_ids("CODE.EXE", [entry.id for entry in eligible[:selected_count]])
                entries = CatalogShortcutResolver(self.catalog).resolve("CODE.EXE", "Ctrl", selection_store=store, language="zh_CN")
                hud = ShortcutHudWindow()
                hud.set_entries("CODE.EXE", "Ctrl", entries, "zh_CN", "Visual Studio Code")
                keys = [
                    label.text() for label in hud.findChildren(QLabel)
                    if label.objectName() == "shortcutHudKey"
                ]
                self.assertEqual(len(keys), 8)
                self.assertEqual(keys, [entry.key for entry in entries[:8]])
                hud.deleteLater()


if __name__ == "__main__":
    unittest.main()
