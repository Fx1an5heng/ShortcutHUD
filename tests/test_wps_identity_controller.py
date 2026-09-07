from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from scripts.shortcut_hud_controller import ShortcutHudController
from scripts.wps_identity import WPS_UNKNOWN


class _Config:
    def __init__(self) -> None:
        self.data = {
            "WPSOFFICE.EXE": {"Ctrl": {"A": "Writer action"}},
            WPS_UNKNOWN: {},
            "DEFAULT": {"Ctrl": {"D": "Default action"}},
            "GLOBAL": {},
        }

    def get_all_shortcuts(self) -> dict[str, object]:
        return self.data

    def get_setting(self, _key: str, default: object = None) -> object:
        return default


class _IdentityState:
    def __init__(self) -> None:
        self.current_app_name: str | None = WPS_UNKNOWN
        self.identity_pending = True


class _Hud:
    def __init__(self) -> None:
        self.visible = False
        self.show_count = 0
        self.hide_count = 0
        self.entries = []

    def isVisible(self) -> bool:
        return self.visible

    def hide(self) -> None:
        self.visible = False
        self.hide_count += 1

    def show_hud(self) -> None:
        self.visible = True
        self.show_count += 1

    def set_entries(self, _app: str, _modifier: str, entries: list, _language: str, _display_name: str | None = None) -> None:
        self.entries = entries


class _WinProxy:
    def current_physical_win_vk(self) -> int | None:
        return None

    def activate_for_current_hold(self, _win_vk: int) -> bool:
        return False


class WpsIdentityControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.identity = _IdentityState()
        self.hud = _Hud()
        self.controller = ShortcutHudController(
            _Config(),
            self.identity,
            self.hud,
            _WinProxy(),
            show_delay_ms=150,
        )

    def tearDown(self) -> None:
        self.controller.stop()

    def test_identity_before_trigger_keeps_original_timer(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.assertTrue(self.controller._show_timer.isActive())

        self.identity.identity_pending = False
        self.identity.current_app_name = "WPSOFFICE.EXE"
        self.controller.on_active_app_changed("WPSOFFICE.EXE")

        self.assertTrue(self.controller._show_timer.isActive())
        self.assertEqual(self.hud.show_count, 0)
        self.controller._show_timer.stop()
        self.controller._show_pending_hud()
        self.assertTrue(self.hud.visible)

    def test_identity_after_elapsed_trigger_shows_without_second_delay(self) -> None:
        self.controller.on_modifiers_changed({"ctrl"})
        self.controller._show_timer.stop()
        self.controller._show_pending_hud()
        self.assertFalse(self.hud.visible)
        self.assertTrue(self.controller._identity_delay_elapsed)

        self.identity.identity_pending = False
        self.identity.current_app_name = "WPSOFFICE.EXE"
        self.controller.on_active_app_changed("WPSOFFICE.EXE")

        self.assertTrue(self.hud.visible)
        self.assertEqual(self.hud.show_count, 1)
        self.assertFalse(self.controller._show_timer.isActive())


if __name__ == "__main__":
    unittest.main()
