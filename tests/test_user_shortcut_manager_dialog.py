from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QTranslator, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
)

from scripts.settings_dialog import SettingsDialog
from scripts.shortcut_resolver import resolve_shortcuts
from scripts.user_shortcut_manager_dialog import (
    ProfileValidationError,
    ShortcutEditDialog,
    UserShortcutManagerDialog,
)
from scripts.user_shortcut_store import LOAD_STATUS_ERROR, UserShortcutStore


class FakeCandidateTracker(QObject):
    candidate_changed = Signal(object)

    def __init__(self, candidate: str | None = None) -> None:
        super().__init__()
        self.candidate = candidate

    @property
    def current_candidate(self) -> str | None:
        return self.candidate

    def editable_candidate(self) -> str | None:
        if self.candidate in {"DEFAULT", "GLOBAL", "WINDOWS_SHELL", "WPS_UNKNOWN"}:
            return None
        return self.candidate

    def set_candidate(self, candidate: str | None) -> None:
        self.candidate = candidate
        self.candidate_changed.emit(candidate)


class UserShortcutManagerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "user_shortcuts.json"
        self.live_store = UserShortcutStore(self.path)
        self.live_store.load()
        self.tracker = FakeCandidateTracker("CODE.EXE")
        self.applied: list[dict[str, object]] = []
        self.dialog = UserShortcutManagerDialog(
            self.live_store,
            self.tracker,
            lambda snapshot: self.applied.append(dict(snapshot)),
        )
        self.dialog._show_warning = lambda _message: None
        self.dialog._show_save_error = lambda _error: None
        self.dialog._confirm = lambda _message: True
        self.addCleanup(self.dialog.close)

    def _install_chinese_translator(self) -> None:
        translator = QTranslator()
        translation_path = (
            Path(__file__).resolve().parents[1]
            / "i18n"
            / "shortcut_overlay_zh_CN.qm"
        )
        self.assertTrue(translator.load(str(translation_path)))
        self.qt_application.installTranslator(translator)
        self.addCleanup(self.qt_application.removeTranslator, translator)
        self._test_translator = translator

    def _make_builtin_manager(self) -> UserShortcutManagerDialog:
        manager = UserShortcutManagerDialog(
            self.live_store,
            self.tracker,
            lambda snapshot: self.applied.append(dict(snapshot)),
            builtin_shortcuts={
                "CODE.EXE": {
                    "Ctrl": {
                        "P": {"en": "Quick Open", "zh": "快速打开"},
                        "H": {"en": "Replace", "zh": "替换"},
                    },
                    "Ctrl+K Ctrl+S": {
                        "": {"en": "Chord", "zh": "多段"}
                    },
                },
                "GLOBAL": {
                    "Ctrl": {"G": {"en": "Global", "zh": "全局"}}
                },
            },
            language="en_US",
        )
        manager._show_warning = lambda _message: None
        manager._show_save_error = lambda _error: None
        manager._confirm = lambda _message: True
        self.addCleanup(manager.close)
        manager.add_current_application()
        return manager

    def _capture_shortcut_validation_message(
        self,
        *,
        modifier: str = "Ctrl",
        key: str,
    ) -> str:
        editor = ShortcutEditDialog(
            modifier=modifier,
            key=key,
            zh="说明",
            en="Description",
        )
        self.addCleanup(editor.close)
        with patch(
            "scripts.user_shortcut_manager_dialog.QMessageBox.warning"
        ) as warning:
            editor._validate_and_accept()
        self.assertTrue(warning.called)
        return warning.call_args.args[2]

    def _capture_duplicate_shortcut_message(self) -> str:
        manager = UserShortcutManagerDialog(
            self.live_store,
            self.tracker,
            lambda _snapshot: None,
        )
        manager._confirm = lambda _message: True
        manager.draft.add_profile("CODE.EXE")
        manager.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "P", "打开", "Open"
        )
        with self.assertRaises(ProfileValidationError) as raised:
            manager.draft.add_shortcut(
                "CODE.EXE", "ctrl", "p", "重复", "Duplicate"
            )
        with patch(
            "scripts.user_shortcut_manager_dialog.QMessageBox.warning"
        ) as warning:
            manager._show_profile_validation_error(raised.exception)
        manager.draft.mark_saved()
        manager.close()
        return warning.call_args.args[2]

    def _capture_save_failure_message(self) -> str:
        with patch(
            "scripts.user_shortcut_manager_dialog.QMessageBox.critical"
        ) as critical:
            UserShortcutManagerDialog._show_save_error(
                self.dialog,
                OSError("sensitive internal error"),
            )
        return critical.call_args.args[2]

    def _capture_unsaved_confirmation_message(self) -> str:
        manager = UserShortcutManagerDialog(
            self.live_store,
            self.tracker,
            lambda _snapshot: None,
        )
        manager.draft.add_profile("CODE.EXE")
        with patch(
            "scripts.user_shortcut_manager_dialog.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question:
            manager.reject()
        message = question.call_args.args[2]
        manager.draft.mark_saved()
        manager.close()
        return message

    def _corrupt_configuration_label_text(self) -> str:
        corrupt_path = Path(self.temporary_directory.name) / "corrupt-i18n.json"
        corrupt_path.write_bytes(b"{broken")
        corrupt_store = UserShortcutStore(corrupt_path)
        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            corrupt_store.load()
        manager = UserShortcutManagerDialog(
            corrupt_store,
            self.tracker,
            lambda _snapshot: None,
        )
        text = manager.corrupt_config_label.text()
        manager.close()
        return text

    def test_phase5b_messages_are_english_without_app_translator(self) -> None:
        self.assertEqual(
            self._capture_shortcut_validation_message(key="F99"),
            "Enter a valid keyboard key, such as P, F5, Enter, or Left.",
        )
        self.assertEqual(
            self._capture_shortcut_validation_message(
                modifier="Ctrl",
                key="Shift",
            ),
            "Shift is a modifier key. Select Ctrl+Shift in Modifier and "
            "enter the action key in Key.",
        )
        self.assertEqual(
            self._capture_shortcut_validation_message(key="Ctrl+W, W"),
            "Only single-step shortcuts are supported in this version.\n"
            "Multi-step/chord shortcuts will be supported in a future version.",
        )
        self.assertEqual(
            self._capture_duplicate_shortcut_message(),
            "This key already exists for the selected modifier combination.",
        )
        self.assertEqual(
            self._capture_save_failure_message(),
            "Save failed. The original configuration was not changed.",
        )
        self.assertEqual(
            self._capture_unsaved_confirmation_message(),
            "There are unsaved changes. Discard them?",
        )
        self.assertEqual(
            self._corrupt_configuration_label_text(),
            "The user configuration file cannot be read. Editing and saving "
            "are disabled to protect the original file.",
        )

    def test_phase5b_messages_are_chinese_with_zh_cn_translator(self) -> None:
        self._install_chinese_translator()

        self.assertEqual(
            self._capture_shortcut_validation_message(key="F99"),
            "请输入有效的键盘按键，例如 P、F5、Enter 或 Left。",
        )
        self.assertEqual(
            self._capture_shortcut_validation_message(
                modifier="Ctrl",
                key="Shift",
            ),
            "Shift 是修饰键。请在‘修饰键’中选择 Ctrl+Shift，并在‘按键’中填写实际按键。",
        )
        self.assertEqual(
            self._capture_shortcut_validation_message(key="Ctrl+W, W"),
            "当前版本仅支持单步快捷键（修饰键 + 一个按键）。"
            "多段快捷键将在后续版本支持。",
        )
        self.assertEqual(
            self._capture_duplicate_shortcut_message(),
            "该修饰键组合下已经存在此按键。",
        )
        self.assertEqual(
            self._capture_save_failure_message(),
            "保存失败，原配置未修改。",
        )
        self.assertEqual(
            self._capture_unsaved_confirmation_message(),
            "存在未保存的修改，确定要放弃吗？",
        )
        self.assertEqual(
            self._corrupt_configuration_label_text(),
            "用户配置文件无法读取。为保护原文件，当前已禁止编辑和保存。",
        )

    def test_settings_has_custom_apps_entry_signal(self) -> None:
        settings = SettingsDialog({})
        self.addCleanup(settings.close)
        requests: list[bool] = []
        settings.custom_apps_requested.connect(lambda: requests.append(True))

        settings.custom_apps_button.click()

        self.assertEqual(requests, [True])

    def test_shortcut_editor_rejects_invalid_key_with_product_message(self) -> None:
        editor = ShortcutEditDialog(key="F99", zh="错误", en="Bad")
        self.addCleanup(editor.close)
        with patch(
            "scripts.user_shortcut_manager_dialog.QMessageBox.warning"
        ) as warning:
            editor._validate_and_accept()

        self.assertNotEqual(editor.result(), QDialog.DialogCode.Accepted)
        self.assertIn(
            "Enter a valid keyboard key",
            warning.call_args.args[2],
        )

    def test_shortcut_editor_explains_modifier_key_belongs_in_modifier_field(self) -> None:
        editor = ShortcutEditDialog(
            modifier="Ctrl",
            key="Shift",
            zh="错误",
            en="Bad",
        )
        self.addCleanup(editor.close)
        with patch(
            "scripts.user_shortcut_manager_dialog.QMessageBox.warning"
        ) as warning:
            editor._validate_and_accept()

        message = warning.call_args.args[2]
        self.assertNotEqual(editor.result(), QDialog.DialogCode.Accepted)
        self.assertIn("Shift is a modifier key", message)
        self.assertIn("Ctrl+Shift", message)

    def test_shortcut_editor_reports_chord_as_future_unsupported_feature(self) -> None:
        for chord in ("Ctrl+W, W", "Ctrl+K Ctrl+S", "g g", "dd"):
            with self.subTest(chord=chord):
                editor = ShortcutEditDialog(key=chord, zh="多段", en="Chord")
                self.addCleanup(editor.close)
                with patch(
                    "scripts.user_shortcut_manager_dialog.QMessageBox.warning"
                ) as warning:
                    editor._validate_and_accept()
                message = warning.call_args.args[2]
                self.assertNotEqual(editor.result(), QDialog.DialogCode.Accepted)
                self.assertIn("Only single-step shortcuts", message)
                self.assertIn("future version", message)

    def test_shortcut_editor_accepts_and_canonicalizes_valid_single_step(self) -> None:
        editor = ShortcutEditDialog(
            modifier="Ctrl+Shift",
            key="f13",
            zh="宏键",
            en="Macro key",
        )
        self.addCleanup(editor.close)

        editor._validate_and_accept()

        self.assertEqual(editor.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(
            editor.values(),
            ("Ctrl+Shift", "F13", "宏键", "Macro key"),
        )

    def test_compiled_chinese_translation_covers_settings_and_manager(self) -> None:
        translator = QTranslator()
        translation_path = (
            Path(__file__).resolve().parents[1]
            / "i18n"
            / "shortcut_overlay_zh_CN.qm"
        )
        self.assertTrue(translator.load(str(translation_path)))
        self.qt_application.installTranslator(translator)
        try:
            settings = SettingsDialog({})
            translated_dialog = UserShortcutManagerDialog(
                self.live_store,
                self.tracker,
                lambda _snapshot: None,
                builtin_shortcuts={
                    "CODE.EXE": {
                        "Ctrl": {
                            "P": {"en": "Quick Open", "zh": "快速打开"}
                        }
                    }
                },
                language="zh_CN",
            )
            translated_dialog._confirm = lambda _message: True
            self.addCleanup(settings.close)
            self.addCleanup(translated_dialog.close)

            self.assertEqual(settings.custom_apps_button.text(), "管理自定义软件...")
            self.assertEqual(translated_dialog.windowTitle(), "自定义软件")
            self.assertEqual(
                translated_dialog.add_current_button.text(), "添加当前软件"
            )
            self.assertEqual(translated_dialog.tabs.tabText(0), "自定义快捷键")
            self.assertEqual(translated_dialog.tabs.tabText(1), "应用内置快捷键")
            self.assertEqual(
                translated_dialog.hide_restore_builtin_button.text(),
                "隐藏应用内置快捷键",
            )
            translated_dialog.add_current_application()
            self.assertEqual(
                translated_dialog.builtin_table.item(0, 2).text(),
                "快速打开",
            )
            self.assertEqual(
                translated_dialog.builtin_table.item(0, 3).text(),
                "显示中",
            )
            self.assertEqual(
                translated_dialog.builtin_scope_note.text(),
                "仅隐藏当前软件提供的内置提示，全局快捷键不受影响。",
            )
        finally:
            self.qt_application.removeTranslator(translator)

    def test_builtin_tab_uses_raw_app_rows_and_marks_unsupported_chord(self) -> None:
        manager = self._make_builtin_manager()

        self.assertEqual(manager.tabs.tabText(0), "Custom Shortcuts")
        self.assertEqual(manager.tabs.tabText(1), "Built-in Shortcuts")
        self.assertEqual(manager.builtin_table.rowCount(), 3)
        self.assertEqual(manager.builtin_table.item(0, 3).text(), "Visible")
        self.assertEqual(
            manager.builtin_table.item(2, 3).text(),
            "Unsupported shortcut type",
        )
        manager.builtin_table.selectRow(2)
        manager._update_builtin_action_state()
        self.assertFalse(manager.hide_restore_builtin_button.isEnabled())

    def test_visible_hidden_restore_flow_changes_only_draft_and_keeps_row(self) -> None:
        manager = self._make_builtin_manager()
        manager.builtin_table.selectRow(0)
        manager._update_builtin_action_state()

        self.assertEqual(
            manager.hide_restore_builtin_button.text(),
            "Hide Built-in Shortcut",
        )
        self.assertTrue(manager.toggle_selected_builtin())

        self.assertTrue(manager.draft.is_builtin_hidden("CODE.EXE", "Ctrl", "P"))
        self.assertEqual(manager.builtin_table.rowCount(), 3)
        self.assertEqual(manager.builtin_table.item(0, 3).text(), "Hidden")
        self.assertEqual(
            manager.hide_restore_builtin_button.text(),
            "Restore Built-in Shortcut",
        )
        self.assertFalse(self.path.exists())
        self.assertEqual(self.live_store.snapshot(), {})
        self.assertEqual(self.applied, [])

        self.assertTrue(manager.toggle_selected_builtin())
        self.assertFalse(manager.draft.is_builtin_hidden("CODE.EXE", "Ctrl", "P"))
        self.assertEqual(manager.builtin_table.item(0, 3).text(), "Visible")

    def test_overridden_builtin_row_remains_visible_with_combined_status(self) -> None:
        manager = self._make_builtin_manager()
        manager.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "P", "用户打开", "User Open"
        )
        manager._render_shortcuts()

        self.assertEqual(manager.builtin_table.rowCount(), 3)
        self.assertEqual(
            manager.builtin_table.item(0, 3).text(),
            "Overridden by Custom Shortcut",
        )
        manager.builtin_table.selectRow(0)
        self.assertTrue(manager.toggle_selected_builtin())
        self.assertEqual(
            manager.builtin_table.item(0, 3).text(),
            "Hidden and Overridden",
        )

    def test_restore_all_preserves_user_and_display_and_clears_stale_state(self) -> None:
        manager = self._make_builtin_manager()
        manager.draft.set_display_name("CODE.EXE", "My Code")
        manager.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "F13", "测试", "Test"
        )
        manager.draft.hide_builtin_shortcut("CODE.EXE", "Ctrl", "P")
        manager.draft.hide_builtin_shortcut("CODE.EXE", "Alt", "F4")
        manager._render_builtin_shortcuts()

        self.assertTrue(manager.restore_all_builtins_button.isEnabled())
        self.assertTrue(manager.restore_all_hidden_builtins())

        profile = manager.draft.get_profile("CODE.EXE")
        self.assertEqual(profile["display_name"], "My Code")
        self.assertIn("F13", profile["shortcuts"]["Ctrl"])
        self.assertNotIn("hidden_builtin", profile)
        self.assertFalse(manager.restore_all_builtins_button.isEnabled())

    def test_cancel_discards_builtin_suppression_without_touching_live_state(self) -> None:
        manager = self._make_builtin_manager()
        manager.builtin_table.selectRow(0)
        self.assertTrue(manager.toggle_selected_builtin())

        manager.reject()

        self.assertFalse(self.path.exists())
        self.assertEqual(self.live_store.snapshot(), {})
        self.assertEqual(self.applied, [])

    def test_save_and_reload_keeps_builtin_hidden(self) -> None:
        manager = self._make_builtin_manager()
        manager.builtin_table.selectRow(1)
        self.assertTrue(manager.toggle_selected_builtin())

        self.assertTrue(manager.save_changes())

        reloaded = UserShortcutStore(self.path)
        snapshot = reloaded.load()
        self.assertEqual(
            snapshot["CODE.EXE"]["hidden_builtin"],
            {"Ctrl": ["H"]},
        )
        entries = resolve_shortcuts(
            {
                "CODE.EXE": {"Ctrl": {"P": "Open", "H": "Replace"}},
                "GLOBAL": {},
            },
            "CODE.EXE",
            "Ctrl",
            snapshot,
        )
        self.assertEqual([entry.key for entry in entries], ["P"])

    def test_failed_suppression_save_keeps_disk_live_runtime_and_draft(self) -> None:
        self.live_store.upsert_profile("CODE.EXE", "Old Code")
        self.live_store.save()
        old_bytes = self.path.read_bytes()
        old_live = self.live_store.snapshot()
        manager = self._make_builtin_manager()
        manager.builtin_table.selectRow(0)
        self.assertTrue(manager.toggle_selected_builtin())
        errors: list[BaseException] = []
        manager._show_save_error = errors.append

        with patch.object(UserShortcutStore, "save", side_effect=OSError("denied")):
            self.assertFalse(manager.save_changes())

        self.assertEqual(self.path.read_bytes(), old_bytes)
        self.assertEqual(self.live_store.snapshot(), old_live)
        self.assertEqual(self.applied, [])
        self.assertTrue(manager.draft.dirty)
        self.assertTrue(manager.draft.is_builtin_hidden("CODE.EXE", "Ctrl", "P"))
        self.assertEqual(len(errors), 1)

    def test_delete_profile_confirmation_describes_all_removed_user_state(self) -> None:
        manager = self._make_builtin_manager()
        messages: list[str] = []
        manager._confirm = lambda message: messages.append(message) or False

        self.assertFalse(manager.delete_selected_profile())

        self.assertEqual(len(messages), 1)
        self.assertIn("custom shortcuts", messages[0])
        self.assertIn("custom display name", messages[0])
        self.assertIn("hidden built-in shortcut records", messages[0])
        self.assertIn("may appear again", messages[0])

    def test_add_current_app_selects_new_profile_and_does_not_duplicate(self) -> None:
        self.assertTrue(self.dialog.add_current_application())
        self.assertEqual(self.dialog.draft.list_profiles(), ["CODE.EXE"])
        self.assertEqual(self.dialog.application_id_label.text(), "CODE.EXE")

        self.assertTrue(self.dialog.add_current_application())
        self.assertEqual(self.dialog.draft.list_profiles(), ["CODE.EXE"])

    def test_reserved_candidate_is_rejected_and_wps_logical_id_is_allowed(self) -> None:
        for identity in ("WINDOWS_SHELL", "WPS_UNKNOWN"):
            with self.subTest(identity=identity):
                self.tracker.set_candidate(identity)
                self.assertFalse(self.dialog.add_current_application())
        self.tracker.set_candidate("WPS_PRESENTATION")

        self.assertTrue(self.dialog.add_current_application())
        self.assertIn("WPS_PRESENTATION", self.dialog.draft.list_profiles())

    def test_cancel_discards_all_draft_changes_without_disk_or_live_mutation(self) -> None:
        self.dialog.add_current_application()
        self.dialog.draft.set_display_name("CODE.EXE", "My Code")
        self.dialog.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "F13", "测试", "Test"
        )

        self.dialog.reject()

        self.assertFalse(self.path.exists())
        self.assertEqual(self.live_store.snapshot(), {})
        self.assertEqual(self.applied, [])

    def test_window_close_can_keep_dirty_editor_open_or_discard_without_saving(self) -> None:
        self.dialog.add_current_application()
        self.dialog.show()
        self.qt_application.processEvents()
        self.dialog._confirm = lambda _message: False

        self.assertFalse(self.dialog.close())
        self.assertTrue(self.dialog.isVisible())
        self.assertFalse(self.path.exists())

        self.dialog._confirm = lambda _message: True
        self.assertTrue(self.dialog.close())
        self.assertFalse(self.path.exists())
        self.assertEqual(self.live_store.snapshot(), {})

    def test_save_persists_then_updates_live_store_and_runtime(self) -> None:
        self.dialog.add_current_application()
        self.dialog.draft.set_display_name("CODE.EXE", "My Code")
        self.dialog.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "F13", "测试", "Test"
        )
        expected = self.dialog.draft.snapshot()

        self.assertTrue(self.dialog.save_changes())

        reloaded = UserShortcutStore(self.path)
        self.assertEqual(reloaded.load(), expected)
        self.assertEqual(self.live_store.snapshot(), expected)
        self.assertEqual(self.applied, [expected])

    def test_saved_override_immediately_participates_in_real_resolution(self) -> None:
        shortcut_data = {
            "CODE.EXE": {
                "Ctrl": {
                    "P": {"en": "Built-in", "zh": "内置"},
                    "B": {"en": "Sidebar", "zh": "侧边栏"},
                }
            },
            "GLOBAL": {"Ctrl": {"G": {"en": "Global", "zh": "全局"}}},
        }
        self.dialog.add_current_application()
        self.dialog.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "P", "用户打开", "User Open"
        )

        self.assertTrue(self.dialog.save_changes())
        entries = resolve_shortcuts(
            shortcut_data,
            "CODE.EXE",
            "Ctrl",
            self.live_store.snapshot(),
        )

        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [("P", "USER_APP"), ("B", "APP"), ("G", "GLOBAL")],
        )

    def test_saved_unknown_profile_suppresses_default_but_keeps_global(self) -> None:
        shortcut_data = {
            "DEFAULT": {"Alt": {"D": {"en": "Default", "zh": "默认"}}},
            "GLOBAL": {"Alt": {"F4": {"en": "Close", "zh": "关闭"}}},
        }
        self.tracker.set_candidate("THIRD_PARTY.EXE")
        self.dialog.add_current_application()
        self.dialog.draft.add_shortcut(
            "THIRD_PARTY.EXE", "Alt", "X", "用户", "User"
        )

        self.assertTrue(self.dialog.save_changes())
        entries = resolve_shortcuts(
            shortcut_data,
            "THIRD_PARTY.EXE",
            "Alt",
            self.live_store.snapshot(),
        )

        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [("X", "USER_APP"), ("F4", "GLOBAL")],
        )

    def test_order_survives_save_and_reload_without_affecting_other_group(self) -> None:
        self.dialog.add_current_application()
        for key in ("P", "F13", "K"):
            self.dialog.draft.add_shortcut(
                "CODE.EXE", "Ctrl", key, f"中文 {key}", f"English {key}"
            )
        self.dialog.draft.add_shortcut(
            "CODE.EXE", "Alt", "Z", "换行", "Wrap"
        )
        self.dialog.draft.move_shortcut("CODE.EXE", "Ctrl", "F13", -1)

        self.assertTrue(self.dialog.save_changes())

        profile = UserShortcutStore(self.path)
        profile.load()
        shortcuts = profile.get_profile("CODE.EXE")["shortcuts"]
        self.assertEqual(list(shortcuts["Ctrl"]), ["F13", "P", "K"])
        self.assertEqual(list(shortcuts["Alt"]), ["Z"])

    def test_failed_save_keeps_disk_live_and_draft_for_retry(self) -> None:
        self.live_store.set_shortcut(
            "CODE.EXE", "Ctrl", "P", "Old", "旧配置"
        )
        self.live_store.save()
        old_bytes = self.path.read_bytes()
        self.dialog.close()
        self.dialog = UserShortcutManagerDialog(
            self.live_store,
            self.tracker,
            lambda snapshot: self.applied.append(dict(snapshot)),
        )
        errors: list[BaseException] = []
        self.dialog._show_save_error = errors.append
        self.dialog._confirm = lambda _message: True
        self.addCleanup(self.dialog.close)
        self.dialog.draft.add_shortcut(
            "CODE.EXE", "Ctrl", "F13", "测试", "Test"
        )
        old_live = self.live_store.snapshot()

        with patch.object(UserShortcutStore, "save", side_effect=OSError("denied")):
            self.assertFalse(self.dialog.save_changes())

        self.assertEqual(self.path.read_bytes(), old_bytes)
        self.assertEqual(self.live_store.snapshot(), old_live)
        self.assertEqual(self.applied, [])
        self.assertTrue(self.dialog.draft.dirty)
        self.assertEqual(len(errors), 1)

    def test_corrupt_json_and_utf8_block_save_without_changing_original(self) -> None:
        for payload in (
            b"{broken",
            b'{"version":1,"apps":{"X":"\xff"}}',
            b'{"version":2,"apps":{"CODE.EXE":[]}}',
            b'{"version":2,"apps":{"CODE.EXE":{"hidden_builtin":"bad"}}}',
            b'{"version":2,"apps":{"CODE.EXE":{"hidden_builtin":{"Ctrl":{}}}}}',
        ):
            with self.subTest(payload=payload):
                self.dialog.close()
                self.path.write_bytes(payload)
                store = UserShortcutStore(self.path)
                with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
                    store.load()
                self.assertEqual(store.load_status, LOAD_STATUS_ERROR)
                dialog = UserShortcutManagerDialog(store, self.tracker, lambda _snapshot: None)
                dialog._show_warning = lambda _message: None
                self.addCleanup(dialog.close)

                self.assertFalse(dialog.save_changes())
                save_button = dialog.button_box.button(
                    QDialogButtonBox.StandardButton.Save
                )
                self.assertFalse(save_button.isEnabled())
                self.assertEqual(self.path.read_bytes(), payload)

    def test_delete_user_override_restores_builtin_entry_after_save(self) -> None:
        shortcuts = {
            "CODE.EXE": {
                "Ctrl": {"P": {"en": "Built-in", "zh": "内置"}}
            },
            "DEFAULT": {"Ctrl": {"D": {"en": "Default", "zh": "默认"}}},
            "GLOBAL": {},
        }
        self.live_store.set_shortcut(
            "CODE.EXE", "Ctrl", "P", "User", "用户"
        )
        self.dialog.close()
        self.dialog = UserShortcutManagerDialog(
            self.live_store,
            self.tracker,
            lambda snapshot: self.applied.append(dict(snapshot)),
        )
        self.addCleanup(self.dialog.close)
        self.dialog.draft.delete_shortcut("CODE.EXE", "Ctrl", "P")

        self.assertTrue(self.dialog.save_changes())
        entries = resolve_shortcuts(
            shortcuts,
            "CODE.EXE",
            "Ctrl",
            self.live_store.snapshot(),
        )
        self.assertEqual([(entry.key, entry.source) for entry in entries], [("P", "APP")])

    def test_delete_unknown_profile_restores_default_layer(self) -> None:
        shortcuts = {
            "DEFAULT": {"Alt": {"D": {"en": "Default", "zh": "默认"}}},
            "GLOBAL": {"Alt": {"F4": {"en": "Close", "zh": "关闭"}}},
        }
        self.live_store.set_shortcut(
            "THIRD_PARTY.EXE", "Alt", "X", "User", "用户"
        )
        self.dialog.close()
        self.tracker.set_candidate("THIRD_PARTY.EXE")
        self.dialog = UserShortcutManagerDialog(
            self.live_store,
            self.tracker,
            lambda snapshot: self.applied.append(dict(snapshot)),
        )
        self.addCleanup(self.dialog.close)
        self.dialog.draft.delete_profile("THIRD_PARTY.EXE")

        self.assertTrue(self.dialog.save_changes())
        entries = resolve_shortcuts(
            shortcuts,
            "THIRD_PARTY.EXE",
            "Alt",
            self.live_store.snapshot(),
        )
        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [("D", "DEFAULT"), ("F4", "GLOBAL")],
        )


if __name__ == "__main__":
    unittest.main()
