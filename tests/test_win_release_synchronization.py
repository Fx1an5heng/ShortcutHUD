import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, Qt

from main import _WinReleaseBridge
from scripts.keyboard_handler import KeyboardHandler
from scripts.win_discovery_proxy import VK_LWIN, WinDiscoveryProxy


class WinReleaseSynchronizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.handler = KeyboardHandler()
        self.bridge = _WinReleaseBridge()
        self.bridge.physical_win_released.connect(
            self.handler.reconcile_win_release,
            type=Qt.ConnectionType.QueuedConnection,
        )
        self.emitted_states: list[set[str]] = []
        self.handler.modifiers_changed.connect(
            lambda modifiers: self.emitted_states.append(set(modifiers))
        )
        self.proxy = WinDiscoveryProxy(
            self.bridge.physical_win_released.emit
        )

    def _process_queued_release(self) -> None:
        QCoreApplication.processEvents()

    def test_active_proxy_release_reconciles_keyboard_handler(self) -> None:
        self.handler._active_modifiers.add("win")
        self.handler._pressed_keys["Win"] = 1.0
        self.proxy._active_win_vk = VK_LWIN

        # Fail-open SendInput proves reconciliation is caused by the explicit
        # physical-release callback, not by observing a synthetic Win-up.
        with (
            patch.object(self.proxy, "_send_one", return_value=False),
            patch.object(self.proxy, "_inject_win", return_value=False),
            patch.object(self.proxy, "_call_next", return_value=0),
        ):
            self.proxy._proxy_win_up(VK_LWIN, 0, 0, 0)
        self._process_queued_release()

        self.assertNotIn("win", self.handler._active_modifiers)
        self.assertNotIn("Win", self.handler._pressed_keys)
        self.assertEqual(self.emitted_states, [set()])

    def test_repeated_release_notification_is_idempotent(self) -> None:
        self.handler._active_modifiers.add("win")

        self.bridge.physical_win_released.emit(VK_LWIN)
        self.bridge.physical_win_released.emit(VK_LWIN)
        self._process_queued_release()

        self.assertNotIn("win", self.handler._active_modifiers)
        self.assertEqual(self.emitted_states, [set()])

    def test_win_release_preserves_other_modifiers(self) -> None:
        self.handler._active_modifiers.update(
            {"win", "ctrl", "alt", "shift"}
        )

        self.bridge.physical_win_released.emit(VK_LWIN)
        self._process_queued_release()

        expected = {"ctrl", "alt", "shift"}
        self.assertEqual(self.handler._active_modifiers, expected)
        self.assertEqual(self.emitted_states, [expected])


if __name__ == "__main__":
    unittest.main()