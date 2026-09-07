from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTranslator, Signal
from PySide6.QtWidgets import QApplication

from scripts.quick_hud_selection_store import QuickHudSelectionStore
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_catalog_resolver import CatalogShortcutResolver
from scripts.shortcut_library_dialog import ShortcutLibraryModel
from scripts.shortcut_library_dialog import ShortcutLibraryDialog
from scripts.application_descriptor import ApplicationDescriptorFactory
from scripts.shell_identity import WINDOWS_DESKTOP
from scripts.user_shortcut_store import UserShortcutStore


_PACK_DIRECTORY = Path(__file__).resolve().parents[1] / "config" / "shortcut_packs"


class _FakeTracker(QObject):
    candidate_changed = Signal(object)
    foreground_context_changed = Signal(object)

    def __init__(self, current, recent=()):
        super().__init__()
        self.current_descriptor = current
        self.center_context = current
        self.recent_descriptors = recent

    def set_current(self, current, recent=()):
        self.current_descriptor = current
        self.center_context = current
        self.recent_descriptors = recent
        self.foreground_context_changed.emit(current)
        self.candidate_changed.emit(current.runtime_identity if current else None)


class ShortcutLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        legacy_path = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        self.catalog = ShortcutCatalog.from_legacy_shortcuts(legacy).with_packs_from(_PACK_DIRECTORY)
        self.temp = TemporaryDirectory()
        self.store = QuickHudSelectionStore(Path(self.temp.name) / "selection.json")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_vscode_pilot_pack_loads_with_unique_stable_ids_and_source(self) -> None:
        entries = [entry for entry in self.catalog.entries if entry.id.startswith("vscode.")]
        self.assertGreaterEqual(len(entries), 40)
        self.assertEqual(len({entry.id for entry in entries}), len(entries))
        self.assertTrue(all(entry.provenance["url"].startswith("https://") for entry in entries))
        self.assertTrue(any(entry.provenance["url"].startswith("https://code.visualstudio.com/") for entry in entries))
        self.assertTrue(any("github.com/microsoft/PowerToys" in entry.provenance["url"] for entry in entries))

    def test_library_application_list_and_localized_rows(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="zh_CN")
        self.assertIn(("CODE.EXE", "Visual Studio Code"), model.applications())
        rows = model.rows("CODE.EXE")
        self.assertGreaterEqual(len(rows), 40)
        terminal = next(row for row in rows if row.entry.id == "vscode.toggle-terminal")
        self.assertEqual(terminal.description, "显示或隐藏集成终端")

    def test_registry_merges_pack_and_legacy_apps_without_process_name_titles(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="en_US")
        labels = dict(model.applications())
        self.assertEqual(labels["CODE.EXE"], "Visual Studio Code")
        self.assertEqual(labels["CHROME.EXE"], "Google Chrome")
        self.assertEqual(labels["3DSMAX.EXE"], "Autodesk 3ds Max")
        self.assertEqual(sum(label == "Visual Studio Code" for label in labels.values()), 1)

    def test_current_and_recent_external_identity_prioritize_vscode_without_blocking_all_apps(self) -> None:
        model = ShortcutLibraryModel(
            self.catalog, self.store, language="en_US",
            current_application="CODE.EXE", recent_applications=("CODE.EXE", "CHROME.EXE"),
        )
        self.assertEqual(model.current_record().display_name, "Visual Studio Code")
        self.assertEqual([record.display_name for record in model.recent_records()], ["Visual Studio Code", "Google Chrome"])
        self.assertIn("Google Chrome", dict(model.applications()).values())

    def test_unsupported_current_identity_keeps_all_supported_apps_available(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, current_application="UNKNOWN.EXE")
        self.assertIsNone(model.current_record())
        self.assertIn("CODE.EXE", dict(model.applications()))

    def test_library_searches_trigger_descriptions_aliases_and_category(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="zh_CN")
        self.assertIn("vscode.toggle-terminal", [row.entry.id for row in model.rows("CODE.EXE", "Ctrl+`")])
        self.assertIn("vscode.find-in-files", [row.entry.id for row in model.rows("CODE.EXE", "workspace files")])
        self.assertIn("vscode.toggle-terminal", [row.entry.id for row in model.rows("CODE.EXE", "集成终端")])
        self.assertIn("vscode.show-source-control", [row.entry.id for row in model.rows("CODE.EXE", "git")])
        self.assertIn("vscode.save", [row.entry.id for row in model.rows("CODE.EXE", "File Management")])

    def test_no_preference_uses_recommended_and_explicit_empty_is_distinct(self) -> None:
        legacy = {"CODE.EXE": {"Ctrl": {"P": "Open"}}, "GLOBAL": {"Ctrl": {"G": "Global"}}}
        catalog = ShortcutCatalog.from_legacy_shortcuts(legacy)
        resolver = CatalogShortcutResolver(catalog)
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=self.store)], ["P", "G"])
        self.store.set_selected_ids("CODE.EXE", [])
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=self.store)], ["G"])
        self.store.clear_selection("CODE.EXE")
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=self.store)], ["P", "G"])

    def test_selection_persists_and_invalid_ids_fail_safe(self) -> None:
        self.store.set_selected_ids("CODE.EXE", ["vscode.open-file", "stale.id"])
        self.store.save()
        reloaded = QuickHudSelectionStore(self.store.path)
        reloaded.load()
        resolver = CatalogShortcutResolver(self.catalog)
        self.assertEqual([entry.key for entry in resolver.resolve("CODE.EXE", "Ctrl", selection_store=reloaded)], ["O"])

    def test_declared_legacy_id_alias_migrates_selection(self) -> None:
        self.store.set_selected_ids("CODE.EXE", ["legacy:app:code.exe:ctrl:s"])
        resolved = CatalogShortcutResolver(self.catalog).resolve("CODE.EXE", "Ctrl", selection_store=self.store)
        self.assertEqual([entry.key for entry in resolved], ["S"])

    def test_model_checkbox_clear_and_restore_recommended(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="en_US")
        self.assertTrue(next(row for row in model.rows("CODE.EXE") if row.entry.id == "vscode.quick-open").checked)
        model.set_checked("CODE.EXE", "vscode.open-file", True)
        self.assertTrue(next(row for row in model.rows("CODE.EXE") if row.entry.id == "vscode.open-file").checked)
        model.clear_all("CODE.EXE")
        self.assertFalse(any(row.checked for row in model.rows("CODE.EXE")))
        model.restore_recommended("CODE.EXE")
        self.assertTrue(next(row for row in model.rows("CODE.EXE") if row.entry.id == "vscode.quick-open").checked)

    def test_catalog_only_single_key_is_browsable_but_cannot_enter_quick_hud_selection(self) -> None:
        model = ShortcutLibraryModel(self.catalog, self.store, language="zh_CN")
        rows = model.rows("EXPLORER.EXE")
        refresh = next(row for row in rows if row.entry.id == "file-explorer.refresh-the-window")
        self.assertEqual(refresh.entry.trigger.keys, ("F5",))
        self.assertFalse(refresh.entry.trigger.is_quick_hud_eligible())
        self.assertFalse(refresh.checked)

        model.set_checked("EXPLORER.EXE", refresh.entry.id, True)
        self.assertIsNone(self.store.selected_ids_for("EXPLORER.EXE"))
        model.restore_recommended("EXPLORER.EXE")
        self.assertTrue(any(row.checked for row in model.rows("EXPLORER.EXE")))

    def test_user_shortcut_is_part_of_same_library_and_keeps_hud_precedence(self) -> None:
        profiles = {"CODE.EXE": {"shortcuts": {"Ctrl": {"P": {"en": "User Open", "zh": "用户打开"}}}}}
        model = ShortcutLibraryModel(self.catalog, self.store, profiles, "zh_CN")
        self.assertEqual(next(row for row in model.rows("CODE.EXE") if row.entry.id.startswith("user:")).source, "user")
        resolved = CatalogShortcutResolver(self.catalog).resolve("CODE.EXE", "Ctrl", profiles, self.store)
        self.assertEqual(resolved[0].description["en"], "User Open")

    def test_user_shortcuts_can_be_added_edited_and_deleted_for_unsupported_app(self) -> None:
        store = UserShortcutStore(Path(self.temp.name) / "user_shortcuts.json")
        store.load()
        model = ShortcutLibraryModel(
            self.catalog,
            self.store,
            language="zh_CN",
            current_descriptor=ApplicationDescriptorFactory().describe("typora.exe"),
            user_store=store,
        )
        model.add_user_shortcut("TYPORA.EXE", "Ctrl", "K", "快捷键", "Shortcut")
        self.assertEqual(model.rows("TYPORA.EXE")[0].source, "user")
        self.assertEqual(store.snapshot()["TYPORA.EXE"]["shortcuts"]["Ctrl"]["K"]["zh"], "快捷键")
        model.edit_user_shortcut("TYPORA.EXE", "Ctrl", "K", "Ctrl", "L", "修改", "Edited")
        self.assertEqual(model.user_shortcut_description("TYPORA.EXE", "Ctrl", "L"), ("修改", "Edited"))
        self.assertTrue(model.delete_user_shortcut("TYPORA.EXE", "Ctrl", "L"))

    def test_pack_categories_are_localized_and_recommendation_does_not_pollute_description(self) -> None:
        zh = ShortcutLibraryModel(self.catalog, self.store, language="zh_CN")
        en = ShortcutLibraryModel(self.catalog, self.store, language="en_US")
        undo = next(row for row in zh.rows("CODE.EXE") if row.entry.id == "vscode.undo")
        self.assertEqual(zh.category_label("basic_editing"), "基础编辑")
        self.assertEqual(zh.category_label("display"), "显示")
        self.assertEqual(en.category_label("basic_editing"), "Basic Editing")
        self.assertEqual(undo.description, "撤销上一次编辑")


class ShortcutLibraryLocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _dialog(self) -> ShortcutLibraryDialog:
        legacy_path = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        catalog = ShortcutCatalog.from_legacy_shortcuts(
            json.loads(legacy_path.read_text(encoding="utf-8"))
        ).with_packs_from(_PACK_DIRECTORY)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return ShortcutLibraryDialog(
            ShortcutLibraryModel(catalog, QuickHudSelectionStore(Path(temporary.name) / "selection.json"), language="zh_CN")
        )

    def test_zh_cn_major_library_labels_are_translated(self) -> None:
        translator = QTranslator()
        self.assertTrue(translator.load(str(Path(__file__).resolve().parents[1] / "i18n" / "shortcut_overlay_zh_CN.qm")))
        self.application.installTranslator(translator)
        try:
            dialog = self._dialog()
            self.assertEqual(dialog.windowTitle(), "快捷键中心")
            self.assertEqual(dialog.search_box.placeholderText(), "搜索快捷键")
            self.assertEqual(dialog.table.horizontalHeaderItem(2).text(), "用途")
            self.assertEqual(dialog.restore_button.text(), "恢复推荐")
            self.assertEqual(dialog.clear_button.text(), "全部取消")
            self.assertEqual(
                dialog._display_name(
                    ApplicationDescriptorFactory().describe(WINDOWS_DESKTOP)
                ),
                "Windows 桌面",
            )
            dialog.deleteLater()
        finally:
            self.application.removeTranslator(translator)

    def test_en_major_library_labels_remain_english(self) -> None:
        dialog = self._dialog()
        self.assertEqual(dialog.windowTitle(), "Shortcut Center")
        self.assertEqual(dialog.search_box.placeholderText(), "Search shortcuts")
        self.assertEqual(dialog.table.horizontalHeaderItem(2).text(), "Description")
        dialog.deleteLater()

    def test_current_vscode_is_auto_selected_and_manual_switch_keeps_search_correct(self) -> None:
        legacy_path = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        catalog = ShortcutCatalog.from_legacy_shortcuts(
            json.loads(legacy_path.read_text(encoding="utf-8"))
        ).with_packs_from(_PACK_DIRECTORY)
        with TemporaryDirectory() as directory:
            model = ShortcutLibraryModel(
                catalog,
                QuickHudSelectionStore(Path(directory) / "selection.json"),
                current_application="CODE.EXE",
                recent_applications=("CODE.EXE", "CHROME.EXE"),
            )
            dialog = ShortcutLibraryDialog(model)
            self.assertEqual(dialog.application_combo.currentData(), "CODE.EXE")
            chrome_index = dialog.application_combo.findData("CHROME.EXE")
            self.assertGreaterEqual(chrome_index, 0)
            dialog.search_box.setText("bookmark")
            dialog.application_combo.setCurrentIndex(chrome_index)
            self.assertGreater(dialog.table.rowCount(), 0)
            self.assertTrue(any(
                "Bookmark" in (dialog.table.item(index, 2).text() if dialog.table.item(index, 2) else "")
                for index in range(dialog.table.rowCount())
            ))
            dialog.deleteLater()

    def test_internal_legacy_category_is_not_presented_to_users(self) -> None:
        catalog = ShortcutCatalog.from_legacy_shortcuts({"NOTEPAD.EXE": {"Ctrl": {"S": "Save"}}})
        with TemporaryDirectory() as directory:
            dialog = ShortcutLibraryDialog(
                ShortcutLibraryModel(catalog, QuickHudSelectionStore(Path(directory) / "selection.json"), language="en_US")
            )
            self.assertEqual(dialog.table.item(0, 3).text(), "Other")
            dialog.deleteLater()

    def test_catalog_only_entry_has_a_disabled_quick_hud_checkbox(self) -> None:
        legacy_path = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        catalog = ShortcutCatalog.from_legacy_shortcuts(
            json.loads(legacy_path.read_text(encoding="utf-8"))
        ).with_packs_from(_PACK_DIRECTORY)
        with TemporaryDirectory() as directory:
            dialog = ShortcutLibraryDialog(
                ShortcutLibraryModel(catalog, QuickHudSelectionStore(Path(directory) / "selection.json"), language="zh_CN")
            )
            explorer_index = dialog.application_combo.findData("EXPLORER.EXE")
            self.assertGreaterEqual(explorer_index, 0)
            dialog.application_combo.setCurrentIndex(explorer_index)
            row_index = next(index for index in range(dialog.table.rowCount()) if dialog.table.item(index, 1).text() == "F5")
            checkbox = dialog.table.item(row_index, 0)
            self.assertFalse(bool(checkbox.flags() & Qt.ItemFlag.ItemIsEnabled))
            dialog.deleteLater()

    def test_follow_current_app_then_manual_pin_and_reenable(self) -> None:
        legacy_path = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        catalog = ShortcutCatalog.from_legacy_shortcuts(
            json.loads(legacy_path.read_text(encoding="utf-8"))
        ).with_packs_from(_PACK_DIRECTORY)
        factory = ApplicationDescriptorFactory()
        vscode = factory.describe("CODE.EXE")
        chrome = factory.describe("CHROME.EXE")
        tracker = _FakeTracker(vscode, (vscode,))
        with TemporaryDirectory() as directory:
            dialog = ShortcutLibraryDialog(
                ShortcutLibraryModel(catalog, QuickHudSelectionStore(Path(directory) / "selection.json"), current_descriptor=vscode),
                candidate_tracker=tracker,
            )
            self.assertEqual(dialog.application_combo.currentData(), "CODE.EXE")
            tracker.set_current(chrome, (chrome, vscode))
            self.assertEqual(dialog.application_combo.currentData(), "CHROME.EXE")
            word_index = dialog.application_combo.findData("WINWORD.EXE")
            self.assertGreaterEqual(word_index, 0)
            dialog.application_combo.setCurrentIndex(word_index)
            self.assertFalse(dialog.follow_current_checkbox.isChecked())
            tracker.set_current(vscode, (vscode, chrome))
            self.assertEqual(dialog.application_combo.currentData(), "WINWORD.EXE")
            dialog.follow_current_checkbox.setChecked(True)
            self.assertEqual(dialog.application_combo.currentData(), "CODE.EXE")
            dialog.deleteLater()

    def test_unsupported_current_application_is_visible_with_empty_builtin_state(self) -> None:
        descriptor = ApplicationDescriptorFactory().describe("typora.exe")
        legacy_path = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        catalog = ShortcutCatalog.from_legacy_shortcuts(
            json.loads(legacy_path.read_text(encoding="utf-8"))
        ).with_packs_from(_PACK_DIRECTORY)
        with TemporaryDirectory() as directory:
            dialog = ShortcutLibraryDialog(
                ShortcutLibraryModel(catalog, QuickHudSelectionStore(Path(directory) / "selection.json"), current_descriptor=descriptor)
            )
            self.assertEqual(dialog.application_combo.currentData(), "TYPORA.EXE")
            self.assertFalse(dialog.empty_builtin_label.isHidden())
            self.assertEqual(dialog.table.rowCount(), 0)
            dialog.deleteLater()

    def test_desktop_context_follows_without_reusing_stale_external_application(self) -> None:
        factory = ApplicationDescriptorFactory()
        vscode = factory.describe("CODE.EXE")
        desktop = factory.describe(WINDOWS_DESKTOP)
        tracker = _FakeTracker(vscode, (vscode,))
        legacy_path = Path(__file__).resolve().parents[1] / "config" / "shortcuts.json"
        catalog = ShortcutCatalog.from_legacy_shortcuts(
            json.loads(legacy_path.read_text(encoding="utf-8"))
        ).with_packs_from(_PACK_DIRECTORY)
        with TemporaryDirectory() as directory:
            dialog = ShortcutLibraryDialog(
                ShortcutLibraryModel(
                    catalog,
                    QuickHudSelectionStore(Path(directory) / "selection.json"),
                    current_descriptor=vscode,
                ),
                candidate_tracker=tracker,
            )
            tracker.set_current(desktop, (vscode,))
            self.assertEqual(dialog.application_combo.currentData(), WINDOWS_DESKTOP)
            self.assertTrue(dialog.empty_builtin_label.isVisible() or not dialog.empty_builtin_label.isHidden())
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
