"""Guide activation, ownership, monitor placement and safe hotkey replacement."""
import ctypes
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, Qt, QTranslator
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame

from scripts.application_descriptor import ApplicationDescriptorFactory
from scripts.full_guide_context import GuideSnapshot, WindowsGuideContext, choose_monitor, guide_geometry
from scripts.full_guide_controller import FullGuideController
from scripts.full_guide_hotkey import FullGuideHotkey, DEFAULT_GUIDE_HOTKEY, WM_HOTKEY, parse_hotkey
from scripts.full_guide_settings import FullGuideSettingsDialog
from scripts.full_guide_window import FullGuideWindow
from scripts.shortcut_catalog_resolver import resolve_catalog_view
from scripts.shortcut_catalog import ShortcutCatalog
from scripts.shortcut_hud_controller import ShortcutHudController
from scripts.suppression_policy import SuppressionPolicy
from main import ShortcutOverlayApplication

ROOT = Path(__file__).resolve().parents[1]


def snapshot(identity="SAMPLE.EXE"):
    return GuideSnapshot(ApplicationDescriptorFactory().describe(identity), 123, "DISPLAY2", (1200, 0, 1400, 900))


class _Backend:
    def __init__(self):
        self.calls = []
        self.available = True
        self.last_error = 1409
        self.altgr = False

    def register(self, identifier, spec):
        self.calls.append(("register", identifier, spec))
        return self.available

    def unregister(self, identifier):
        self.calls.append(("unregister", identifier))

    def altgr_down(self):
        return self.altgr


class GuideHotkeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def make(self):
        backend = _Backend()
        service = FullGuideHotkey(self.qt, backend=backend)
        self.addCleanup(service.close)
        return service, backend

    def test_default_valid_and_bare_modifiers_reserved_rejected(self):
        self.assertEqual(parse_hotkey(DEFAULT_GUIDE_HOTKEY).vk, 0x79)
        for text in ("Ctrl", "Alt", "Win", "Shift", "F5", "Win+L", "Ctrl+F12", "Ctrl+K, Ctrl+S", "Alt+Tab", "Ctrl+Alt+Delete"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_hotkey(text)

    def test_registration_conflict_retains_previous_key(self):
        service, backend = self.make()
        self.assertTrue(service.configure(DEFAULT_GUIDE_HOTKEY))
        previous = service.identifier
        backend.available = False
        self.assertFalse(service.configure("Ctrl+Shift+F9"))
        self.assertEqual(service.identifier, previous)
        self.assertEqual(service.spec.text, DEFAULT_GUIDE_HOTKEY)
        self.assertFalse(any(c[0] == "unregister" for c in backend.calls))

    def test_initial_registration_failure_is_safe(self):
        service, backend = self.make()
        backend.available = False
        self.assertFalse(service.configure(DEFAULT_GUIDE_HOTKEY))
        self.assertIsNone(service.identifier)
        self.assertFalse(service.handle_message(0x5348))

    def test_native_dispatch_only_for_registered_id(self):
        service, _ = self.make()
        service.configure(DEFAULT_GUIDE_HOTKEY)
        calls = []
        service.activated.connect(lambda: calls.append(True))
        message = wintypes.MSG()
        message.message, message.wParam = WM_HOTKEY, service.identifier
        self.assertEqual(service._filter.nativeEventFilter(b"windows_dispatcher_MSG", ctypes.addressof(message)), (True, 0))
        self.assertEqual(calls, [True])
        self.assertFalse(service.handle_message(1))

    def test_altgr_never_activates(self):
        service, backend = self.make()
        service.configure(DEFAULT_GUIDE_HOTKEY)
        callback = Mock()
        service.activated.connect(callback)
        backend.altgr = True
        service.handle_message(service.identifier)
        callback.assert_not_called()

    def test_reconfigure_registers_new_before_unregistering_old(self):
        service, backend = self.make()
        service.configure(DEFAULT_GUIDE_HOTKEY)
        service.configure("Ctrl+Shift+F9")
        self.assertEqual([c[0] for c in backend.calls], ["register", "register", "unregister"])

    def test_settings_conflict_stays_open_without_accept(self):
        callback = Mock(return_value=(False, "1409"))
        dialog = FullGuideSettingsDialog(DEFAULT_GUIDE_HOTKEY, callback)
        self.addCleanup(dialog.close)
        dialog.save()
        self.assertIn("1409", dialog.status.text())
        self.assertEqual(dialog.result(), 0)

    def test_modal_settings_owns_input_until_dismissed(self):
        controller = SimpleNamespace(active=False, toggle=Mock())
        app = SimpleNamespace(full_guide_controller=controller, activeModalWidget=lambda: object())
        ShortcutOverlayApplication.toggle_full_guide(app)
        controller.toggle.assert_not_called()
        app.activeModalWidget = lambda: None
        ShortcutOverlayApplication.toggle_full_guide(app)
        controller.toggle.assert_called_once()


class GuideInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def make(self):
        catalog = ShortcutCatalog.from_legacy_shortcuts({"SAMPLE.EXE": {"Ctrl": {"S": "Save"}}})
        policy = SuppressionPolicy()
        hud = Mock()
        hud.isVisible.return_value = True
        config = SimpleNamespace(get_shortcut_catalog=lambda: catalog, get_setting=lambda _key, default=None: default)
        quick = ShortcutHudController(config, SimpleNamespace(current_app_name="SAMPLE.EXE"), hud, Mock(), suppression_policy=policy)
        view = FullGuideWindow()
        provider = Mock(return_value=snapshot())
        guide = FullGuideController(view, quick, policy, provider, lambda: catalog, lambda: {}, lambda: "en")
        self.addCleanup(quick.stop)
        self.addCleanup(view.close)
        return guide, view, quick, policy, provider, hud

    def test_open_captures_before_present_and_self_does_not_replace_snapshot(self):
        guide, view, _, _, provider, _ = self.make()
        with patch.object(view, "present") as present:
            guide.toggle()
            original = guide.snapshot
            present.assert_called_once()
            provider.return_value = snapshot("SHORTCUTHUD.EXE")
            self.assertIs(guide.snapshot, original)
            self.assertEqual(provider.call_count, 1)
            guide.close()

    def test_toggle_closes_and_clears_snapshot(self):
        guide, view, quick, _, provider, _ = self.make()
        with patch.object(view, "present"):
            guide.toggle()
            guide.toggle()
        self.assertFalse(guide.active)
        self.assertIsNone(guide.snapshot)
        self.assertFalse(quick._guide_active)
        self.assertEqual(provider.call_count, 1)

    def test_pending_and_visible_quick_hud_canceled_on_open(self):
        guide, view, quick, _, _, hud = self.make()
        quick.on_modifiers_changed({"Ctrl"})
        quick._show_timer.start(150)
        with patch.object(view, "present"):
            guide.toggle()
            self.assertFalse(quick._show_timer.isActive())
            hud.hide.assert_called()
            quick.on_modifiers_changed({"Ctrl", "Shift"})
            quick._show_pending_hud()
            self.assertFalse(quick._show_timer.isActive())
            hud.show_hud.assert_not_called()
            guide.close()

    def test_close_requires_fresh_hold_then_quick_hud_works(self):
        guide, view, quick, _, _, hud = self.make()
        hud.isVisible.return_value = False
        quick.on_modifiers_changed({"Ctrl"})
        with patch.object(view, "present"):
            guide.toggle()
            guide.close()
        self.assertFalse(quick._show_timer.isActive())
        quick.on_modifiers_changed(set())
        quick.on_modifiers_changed({"Ctrl"})
        self.assertTrue(quick._show_timer.isActive())

    def test_hard_block_prevents_open_and_closes_open_session(self):
        guide, view, _, policy, provider, _ = self.make()
        policy.set_manual_game_mode(True)
        guide.toggle()
        provider.assert_not_called()
        policy.set_manual_game_mode(False)
        with patch.object(view, "present"):
            guide.toggle()
            policy.set_manual_game_mode(True)
            guide.on_suppression_changed()
        self.assertFalse(guide.active)

    def test_soft_block_allows_explicit_guide(self):
        guide, view, _, policy, _, _ = self.make()
        policy.set_runtime_sources(fullscreen_active=True, excluded_app_active=True)
        with patch.object(view, "present"):
            guide.toggle()
            self.assertTrue(guide.active)
            guide.close()

    def test_escape_clears_search_then_closes(self):
        guide, view, _, _, _, _ = self.make()
        guide.toggle()
        view.search_box.setText("save")
        view.escape()
        self.assertEqual(view.search_box.text(), "")
        self.assertTrue(guide.active)
        view.escape()
        self.assertFalse(guide.active)

    def test_deactivate_closes_without_reopening(self):
        guide, view, _, _, provider, _ = self.make()
        guide.toggle()
        QApplication.sendEvent(view, QEvent(QEvent.Type.WindowDeactivate))
        self.assertFalse(guide.active)
        self.assertFalse(view.isVisible())
        self.assertEqual(provider.call_count, 1)

    def test_chinese_controls_and_large_window(self):
        translator = QTranslator()
        self.assertTrue(translator.load(str(ROOT / "i18n/shortcut_overlay_zh_CN.qm")))
        self.qt.installTranslator(translator)
        try:
            guide, view, _, _, _, _ = self.make()
            guide.toggle()
            self.assertIn("搜索", view.search_box.placeholderText())
            self.assertIn("已收录", view.count_label.text())
            self.assertGreater(view.width(), 1200)
            self.assertGreater(view.x(), 1200)
            self.assertEqual(view.scroll.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        finally:
            self.qt.removeTranslator(translator)

    def test_no_pack_disk_read_on_present_or_search(self):
        guide, view, _, _, _, _ = self.make()
        with patch.object(ShortcutCatalog, "load_packs", side_effect=AssertionError("disk reload")):
            guide.toggle()
            view.search_box.setText("save")
            view._render_sections()
            self.assertTrue(view.sections)
            view.search_box.clear()
            view._render_sections()
            self.assertEqual(sum(len(s.rows) for s in view.sections), 1)

    def test_reused_window_follows_locale_change(self):
        guide, view, _, _, _, _ = self.make()
        self.assertEqual(view.search_box.placeholderText(), "Search shortcuts…")
        translator = QTranslator()
        self.assertTrue(translator.load(str(ROOT / "i18n/shortcut_overlay_zh_CN.qm")))
        self.qt.installTranslator(translator)
        try:
            self.qt.processEvents()
            self.assertIn("搜索", view.search_box.placeholderText())
            self.assertEqual(view.columns_box.itemText(0), "自动列数")
        finally:
            self.qt.removeTranslator(translator)
            self.qt.processEvents()
        self.assertEqual(view.search_box.placeholderText(), "Search shortcuts…")

    def test_keyboard_shortcuts_focus_search_clear_then_close(self):
        guide, view, _, _, _, _ = self.make()
        guide.toggle()
        self.qt.setActiveWindow(view)
        view.close_button.setFocus()
        QTest.keyClick(view, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(view.search_box.hasFocus())
        view.search_box.setText("save")
        QTest.keyClick(view.search_box, Qt.Key.Key_Escape)
        self.assertEqual(view.search_box.text(), "")
        self.assertTrue(guide.active)
        QTest.keyClick(view.search_box, Qt.Key.Key_Escape)
        self.assertFalse(guide.active)

    def test_unknown_after_known_app_does_not_retain_rows(self):
        guide, view, _, _, provider, _ = self.make()
        guide.toggle()
        self.assertTrue(view.rows)
        guide.close()
        provider.return_value = snapshot("UNKNOWN.EXE")
        guide.toggle()
        self.assertFalse(view.rows)
        self.assertTrue(view.empty_panel.isVisible())
        self.assertTrue(view.center_button.isVisible())
        self.assertEqual(view.app_label.text(), "Unknown")

    def test_guide_resets_win_discovery_and_does_not_rearm_held_win(self):
        guide, view, quick, _, _, _ = self.make()
        quick.on_modifiers_changed({"Win"})
        quick._win_discovery_active = True
        with patch.object(view, "present"):
            guide.toggle()
            self.assertFalse(quick._win_discovery_active)
            self.assertFalse(quick._win_activation_attempted)
            self.assertFalse(quick._show_timer.isActive())
            guide.close()
        self.assertFalse(quick._show_timer.isActive())
        self.assertTrue(quick._suppression_rearm_required)

    def test_real_layout_rebalances_three_four_five_without_horizontal_scroll(self):
        guide, view, _, _, _, _ = self.make()
        catalog = ShortcutCatalog.load_packs(ROOT / "config/shortcut_packs")
        rows = resolve_catalog_view(catalog, "CODE.EXE", language="zh_CN")
        view.present(GuideSnapshot(snapshot().descriptor, 0, "wide", (0, 0, 1920, 1040)), rows)
        for index, columns in enumerate((3, 4, 5), 1):
            view.columns_box.setCurrentIndex(index)
            QTest.qWait(70)
            self.assertEqual(len(view.rendered_columns), columns)
            self.assertEqual(sum(len(s.rows) for c in view.rendered_columns for s in c), 133)
            self.assertEqual(view.scroll.horizontalScrollBar().maximum(), 0)
        view.resize(1120, 780)
        QTest.qWait(100)
        self.assertEqual(len(view.rendered_columns), 3)
        self.assertGreater(view.scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(view.scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(len(view.findChildren(QFrame, "guideRow")), 133)


class GuideMonitorTests(unittest.TestCase):
    def test_second_monitor_device_wins_cursor_primary(self):
        screens = [("DISPLAY1", (0, 0, 1920, 1040)), ("DISPLAY2", (1920, 0, 1440, 860))]
        self.assertEqual(choose_monitor(screens, "DISPLAY2", (10, 10)), screens[1])

    def test_desktop_invalid_hwnd_uses_cursor_monitor(self):
        screens = [("DISPLAY1", (0, 0, 1920, 1040)), ("DISPLAY2", (-1440, 0, 1440, 860))]
        self.assertEqual(choose_monitor(screens, None, (-500, 200)), screens[1])
        self.assertEqual(choose_monitor(screens, None, (99999, 99999)), screens[0])

    def test_geometry_uses_available_logical_coordinates(self):
        rect = guide_geometry((-1440, 0, 1440, 860))
        self.assertGreater(rect.x(), -1440)
        self.assertLessEqual(rect.right(), 0)
        self.assertLess(rect.height(), 860)

    def test_capture_refreshes_foreground_before_building_descriptor(self):
        qt = QApplication.instance() or QApplication([])
        runtime = SimpleNamespace(current_app_name="OLD.EXE")
        monitor = SimpleNamespace(current_hwnd=123, current_executable_path=None)
        monitor.check_foreground_app = lambda: setattr(runtime, "current_app_name", "NEW.EXE")
        provider = WindowsGuideContext(monitor, runtime, SimpleNamespace(center_context=None), lambda: ShortcutCatalog(), lambda: {}, lambda: "en")
        with patch("scripts.full_guide_context.win32process.GetWindowThreadProcessId", return_value=(1, 999999)):
            captured = provider.capture()
        self.assertEqual(captured.descriptor.runtime_identity, "NEW.EXE")
        self.assertEqual(captured.hwnd, 123)


if __name__ == "__main__":
    unittest.main()
