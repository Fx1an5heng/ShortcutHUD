import time
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from scripts.shortcut_hud_controller import ShortcutHudController
from scripts.keyboard_handler import KeyboardHandler
from scripts.win_discovery_proxy import VK_LWIN


class _FakeConfigManager:
    def __init__(self, shortcuts: dict[str, object]) -> None:
        self.shortcuts = shortcuts

    def get_all_shortcuts(self) -> dict[str, object]:
        return self.shortcuts.copy()

    def get_setting(self, key: str, default: object = None) -> object:
        return "zh_CN" if key == "language" else default


class _FakeForegroundMonitor:
    def __init__(self, current_app_name: str | None = "CODE.EXE") -> None:
        self.current_app_name = current_app_name


class _FakeHudWindow:
    def __init__(self) -> None:
        self.visible = False
        self.show_calls = 0
        self.hide_calls = 0
        self.rendered: list[tuple[str, str, list[object], str | None]] = []

    def isVisible(self) -> bool:
        return self.visible

    def hide(self) -> None:
        self.visible = False
        self.hide_calls += 1

    def show_hud(self) -> None:
        self.visible = True
        self.show_calls += 1

    def set_entries(
        self,
        application_name: str,
        modifier_combination: str,
        entries: list[object],
        language: str | None,
    ) -> None:
        self.rendered.append(
            (application_name, modifier_combination, entries, language)
        )


class _FakeWinDiscoveryProxy:
    def __init__(self) -> None:
        self.current_win_vk: int | None = None
        self.activation_result = True
        self.activation_calls: list[int] = []
        self.session_active = False

    def current_physical_win_vk(self) -> int | None:
        return self.current_win_vk

    def activate_for_current_hold(self, win_vk: int) -> bool:
        self.activation_calls.append(win_vk)
        if self.activation_result:
            self.session_active = True
        return self.activation_result


def wait_until(predicate, timeout_ms: int = 500) -> bool:
    """Poll a predicate while servicing the Qt event loop, with a bound.

    Returns True as soon as the predicate holds and False on timeout.
    Waiting happens in short event-processing slices so Qt timers and
    queued signals can fire, without one long blocking sleep.
    """

    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        QTest.qWait(5)


class ShortcutHudControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.config = _FakeConfigManager(
            {
                "CODE.EXE": {
                    "Ctrl": {"S": "Save"},
                    "Ctrl+Shift": {"S": "Save As"},
                },
                "DEFAULT": {"Ctrl": {"C": "Copy"}},
            }
        )
        self.monitor = _FakeForegroundMonitor()
        self.hud = _FakeHudWindow()
        self.proxy = _FakeWinDiscoveryProxy()
        self.controller = ShortcutHudController(
            self.config,
            self.monitor,
            self.hud,
            self.proxy,
            show_delay_ms=20,
            win_only_show_delay_ms=40,
        )

    def tearDown(self) -> None:
        self.controller.stop()

    def _enable_win_shortcuts(self) -> None:
        self.config.shortcuts["CODE.EXE"]["Win"] = {"R": "Run"}

    def _show_win_discovery(self) -> None:
        self._enable_win_shortcuts()
        self.proxy.current_win_vk = VK_LWIN
        self.controller.on_modifiers_changed({"win"})
        self.assertTrue(
            wait_until(lambda: self.hud.visible),
            "Win discovery HUD did not appear in time",
        )

    def test_quick_release_cancels_pending_show(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.controller.on_modifiers_changed(set())
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertFalse(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 0)

    def test_pending_transition_uses_latest_modifier_state(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        time.sleep(0.005)
        self.controller.on_modifiers_changed({"ctrl", "shift"})
        self.assertTrue(wait_until(lambda: self.hud.visible))

        self.assertTrue(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 1)
        self.assertEqual(self.hud.rendered[-1][1], "Ctrl+Shift")

    def test_visible_transition_updates_same_hud_without_second_show(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.assertTrue(wait_until(lambda: self.hud.visible))
        self.controller.on_modifiers_changed({"ctrl", "shift"})

        self.assertTrue(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 1)
        self.assertEqual(self.hud.rendered[-1][1], "Ctrl+Shift")

    def test_empty_resolution_hides_visible_hud(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.assertTrue(wait_until(lambda: self.hud.visible))
        self.controller.on_modifiers_changed({"alt"})

        self.assertFalse(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 1)

    def test_foreground_change_uses_monitored_state(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.assertTrue(wait_until(lambda: self.hud.visible))
        self.monitor.current_app_name = None
        self.controller.on_active_app_changed("DEFAULT")

        self.assertEqual(self.hud.show_calls, 1)
        self.assertEqual(self.hud.rendered[-1][0], "DEFAULT")
        self.assertEqual(self.hud.rendered[-1][2][0].key, "C")

    def test_result_empty_result_can_show_again(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.assertTrue(wait_until(lambda: self.hud.visible))
        self.controller.on_modifiers_changed({"alt"})
        self.controller.on_modifiers_changed({"ctrl"})
        self.assertTrue(wait_until(lambda: self.hud.visible))

        self.assertTrue(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 2)

    def test_timer_re_resolves_and_does_not_show_stale_results(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.config.shortcuts["CODE.EXE"]["Ctrl"] = {}
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertFalse(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 0)

    def test_stop_cancels_timer_hides_hud_and_clears_state(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.controller.stop()
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertFalse(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 0)
        self.assertFalse(self.controller._show_timer.isActive())
        self.assertIsNone(self.controller._current_modifier)

    def test_win_threshold_not_reached_does_not_activate_proxy(self) -> None:
        self._enable_win_shortcuts()
        self.proxy.current_win_vk = VK_LWIN
        self.controller.on_modifiers_changed({"win"})
        time.sleep(0.01)
        self.controller.on_modifiers_changed(set())
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertEqual(self.proxy.activation_calls, [])
        self.assertEqual(self.hud.show_calls, 0)

    def test_win_threshold_with_no_entries_does_not_activate_proxy(self) -> None:
        self.proxy.current_win_vk = VK_LWIN
        self.controller.on_modifiers_changed({"win"})
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertEqual(self.proxy.activation_calls, [])
        self.assertEqual(self.hud.show_calls, 0)

    def test_win_threshold_rechecks_physical_key_before_activation(self) -> None:
        self._enable_win_shortcuts()
        self.proxy.current_win_vk = None
        self.controller.on_modifiers_changed({"win"})
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertEqual(self.proxy.activation_calls, [])
        self.assertEqual(self.hud.show_calls, 0)

    def test_successful_win_hold_activates_once_then_shows_hud(self) -> None:
        self._show_win_discovery()
        self.controller.refresh_current_state()

        self.assertTrue(self.hud.visible)
        self.assertEqual(self.proxy.activation_calls, [VK_LWIN])
        self.assertEqual(self.hud.show_calls, 1)

    def test_win_proxy_activation_failure_is_fail_open_without_hud(self) -> None:
        self._enable_win_shortcuts()
        self.proxy.current_win_vk = VK_LWIN
        self.proxy.activation_result = False
        self.controller.on_modifiers_changed({"win"})
        self.assertTrue(wait_until(lambda: bool(self.proxy.activation_calls)))
        self.controller.refresh_current_state()
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertEqual(self.proxy.activation_calls, [VK_LWIN])
        self.assertFalse(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 0)

    def test_non_modifier_down_hides_win_hud_without_ending_proxy(self) -> None:
        self._show_win_discovery()

        self.controller.on_key_event("R", "down")

        self.assertFalse(self.hud.visible)
        self.assertTrue(self.proxy.session_active)
        self.assertTrue(self.controller._win_execution_seen)

    def test_modifier_down_does_not_hide_win_discovery_hud(self) -> None:
        self._show_win_discovery()

        self.controller.on_key_event("Shift", "down")

        self.assertTrue(self.hud.visible)
        self.assertFalse(self.controller._win_execution_seen)

    def test_win_release_resets_controller_but_proxy_owns_session_close(self) -> None:
        self._show_win_discovery()

        self.controller.on_modifiers_changed(set())

        self.assertFalse(self.hud.visible)
        self.assertFalse(self.controller._win_discovery_active)
        self.assertTrue(self.proxy.session_active)

    def test_reconciled_win_release_hides_hud_through_modifier_signal(self) -> None:
        self._show_win_discovery()
        handler = KeyboardHandler()
        handler._active_modifiers.add("win")
        handler.modifiers_changed.connect(self.controller.on_modifiers_changed)

        handler.reconcile_win_release(VK_LWIN)

        self.assertFalse(self.hud.visible)
        self.assertNotIn("win", handler._active_modifiers)

    def test_controller_stop_does_not_stop_proxy_lifecycle(self) -> None:
        self._show_win_discovery()

        self.controller.stop()

        self.assertFalse(self.hud.visible)
        self.assertTrue(self.proxy.session_active)

    def test_ctrl_hold_never_activates_win_proxy(self) -> None:
        self.proxy.current_win_vk = VK_LWIN
        self.controller.on_modifiers_changed({"ctrl"})
        self.assertTrue(wait_until(lambda: self.hud.visible))

        self.assertEqual(self.proxy.activation_calls, [])
        self.assertTrue(self.hud.visible)


    def test_empty_windows_shell_ctrl_does_not_fall_back_or_show_hud(self) -> None:
        self.monitor.current_app_name = "WINDOWS_SHELL"
        self.config.shortcuts = {
            "WINDOWS_SHELL": {},
            "DEFAULT": {"Ctrl": {"C": "Copy"}},
            "GLOBAL": {"Win": {"R": "Run"}},
        }

        self.controller.on_modifiers_changed({"ctrl"})
        self.assertFalse(wait_until(lambda: self.hud.visible))

        self.assertFalse(self.hud.visible)
        self.assertEqual(self.hud.show_calls, 0)
        self.assertEqual(self.hud.rendered, [])


    def test_unknown_app_alt_passes_default_and_global_entries_to_hud(self) -> None:
        self.monitor.current_app_name = "UNKNOWN_THIRD_PARTY.EXE"
        self.config.shortcuts = {
            "DEFAULT": {"Alt": {"ESC": "Local fallback"}},
            "GLOBAL": {
                "Alt": {
                    "Tab": "Switch windows",
                    "F4": "Close current window",
                }
            },
        }

        self.controller.on_modifiers_changed({"alt"})
        self.assertTrue(wait_until(lambda: self.hud.visible))

        self.assertTrue(self.hud.visible)
        entries = self.hud.rendered[-1][2]
        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [
                ("ESC", "DEFAULT"),
                ("Tab", "GLOBAL"),
                ("F4", "GLOBAL"),
            ],
        )

    def test_known_app_without_alt_passes_global_only_to_hud(self) -> None:
        self.monitor.current_app_name = "KNOWN_APP_WITHOUT_ALT"
        self.config.shortcuts = {
            "KNOWN_APP_WITHOUT_ALT": {"Ctrl": {"K": "Known local"}},
            "DEFAULT": {"Alt": {"ESC": "Fallback must not apply"}},
            "GLOBAL": {
                "Alt": {
                    "Tab": "Switch windows",
                    "F4": "Close current window",
                }
            },
        }

        self.controller.on_modifiers_changed({"alt"})
        self.assertTrue(wait_until(lambda: self.hud.visible))

        self.assertTrue(self.hud.visible)
        entries = self.hud.rendered[-1][2]
        self.assertEqual(
            [(entry.key, entry.source) for entry in entries],
            [("Tab", "GLOBAL"), ("F4", "GLOBAL")],
        )


if __name__ == "__main__":
    unittest.main()
