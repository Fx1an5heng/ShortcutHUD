import tempfile
from pathlib import Path
import unittest

from PySide6.QtWidgets import QApplication

from scripts.config_manager import ConfigManager
from scripts.game_guard_runtime import GameGuardRuntime
from scripts.suppression_policy import SuppressionDecision, SuppressionPolicy


class _FakeFullscreenDetector:
    def __init__(self, result: bool = False) -> None:
        self.result = result
        self.calls: list[int] = []

    def is_fullscreen(self, hwnd: object) -> bool:
        self.calls.append(int(hwnd))
        return self.result


class GameGuardRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def _make_runtime(
        self,
        *,
        identity: str | None = "CODE.EXE",
        fullscreen: bool = False,
        settings: dict[str, object] | None = None,
    ) -> tuple[
        GameGuardRuntime,
        SuppressionPolicy,
        _FakeFullscreenDetector,
        list[str | None],
    ]:
        current_identity = [identity]
        policy = SuppressionPolicy()
        detector = _FakeFullscreenDetector(fullscreen)
        runtime = GameGuardRuntime(
            policy,
            detector,
            lambda: current_identity[0],
            settings or {},
        )
        self.addCleanup(runtime.deleteLater)
        return runtime, policy, detector, current_identity

    def test_fullscreen_tick_sets_soft_block(self) -> None:
        runtime, policy, _detector, _identity = self._make_runtime(
            fullscreen=True,
            settings={"fullscreen_suppression_enabled": True},
        )

        runtime.on_foreground_polled(101, "code.exe")

        self.assertTrue(runtime.fullscreen_active)
        self.assertIs(policy.decision, SuppressionDecision.SOFT_BLOCK)

    def test_same_hwnd_is_rechecked_when_fullscreen_changes(self) -> None:
        runtime, policy, detector, _identity = self._make_runtime(
            settings={"fullscreen_suppression_enabled": True}
        )
        runtime.on_foreground_polled(101, "code.exe")
        detector.result = True

        runtime.on_foreground_polled(101, "code.exe")

        self.assertEqual(detector.calls, [101, 101])
        self.assertIs(policy.decision, SuppressionDecision.SOFT_BLOCK)

    def test_disabled_fullscreen_setting_skips_detection(self) -> None:
        runtime, policy, detector, _identity = self._make_runtime(
            fullscreen=True,
            settings={"fullscreen_suppression_enabled": False},
        )

        runtime.on_foreground_polled(101, "code.exe")

        self.assertEqual(detector.calls, [])
        self.assertFalse(runtime.fullscreen_active)
        self.assertIs(policy.decision, SuppressionDecision.ALLOW)

    def test_default_fullscreen_setting_is_opt_in_and_skips_detection(self) -> None:
        runtime, policy, detector, _identity = self._make_runtime(fullscreen=True)

        runtime.on_foreground_polled(101, "code.exe")

        self.assertFalse(runtime.fullscreen_suppression_enabled)
        self.assertEqual(detector.calls, [])
        self.assertIs(policy.decision, SuppressionDecision.ALLOW)

    def test_current_excluded_app_sets_soft_block(self) -> None:
        runtime, policy, _detector, _identity = self._make_runtime(
            settings={"excluded_applications": ["code.exe"]}
        )

        runtime.on_foreground_polled(101, "code.exe")

        self.assertTrue(runtime.excluded_app_active)
        self.assertIs(policy.decision, SuppressionDecision.SOFT_BLOCK)

    def test_removing_current_exclusion_returns_allow(self) -> None:
        runtime, policy, _detector, _identity = self._make_runtime(
            settings={"excluded_applications": ["code.exe"]}
        )
        runtime.on_foreground_polled(101, "code.exe")

        runtime.update_settings({"excluded_applications": []})

        self.assertFalse(runtime.excluded_app_active)
        self.assertIs(policy.decision, SuppressionDecision.ALLOW)

    def test_unrelated_app_is_not_suppressed(self) -> None:
        runtime, policy, _detector, _identity = self._make_runtime(
            identity="NOTEPAD.EXE",
            settings={"excluded_applications": ["code.exe"]},
        )

        runtime.on_foreground_polled(101, "notepad.exe")

        self.assertFalse(runtime.excluded_app_active)
        self.assertIs(policy.decision, SuppressionDecision.ALLOW)

    def test_logical_identity_change_updates_exclusion_without_waiting_for_tick(self) -> None:
        runtime, policy, _detector, _identity = self._make_runtime(
            settings={"excluded_applications": ["wps.exe"]}
        )
        runtime.on_foreground_polled(101, "wps.exe")

        runtime.on_active_app_changed("WPS.EXE")

        self.assertTrue(runtime.excluded_app_active)
        self.assertIs(policy.decision, SuppressionDecision.SOFT_BLOCK)

    def test_manual_off_falls_back_to_remaining_fullscreen_source(self) -> None:
        runtime, policy, _detector, _identity = self._make_runtime(
            fullscreen=True,
            settings={"fullscreen_suppression_enabled": True},
        )
        runtime.on_foreground_polled(101, "code.exe")
        runtime.set_manual_game_mode(True)

        runtime.set_manual_game_mode(False)

        self.assertIs(policy.decision, SuppressionDecision.SOFT_BLOCK)

    def test_effective_change_signal_ignores_lower_priority_source_churn(self) -> None:
        runtime, _policy, detector, _identity = self._make_runtime(
            settings={"fullscreen_suppression_enabled": True}
        )
        changes = []
        runtime.suppression_changed.connect(lambda: changes.append(True))
        runtime.set_manual_game_mode(True)
        detector.result = True

        runtime.on_foreground_polled(101, "code.exe")

        self.assertEqual(changes, [True])


class GameGuardConfigPersistenceTests(unittest.TestCase):
    def test_exclusion_persists_through_config_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = ConfigManager(
                str(root / "shortcuts.json"),
                str(root / "settings.json"),
            )
            first.initialize_configs()
            first.update_settings(
                {
                    "excluded_applications": [
                        "C:/Program Files/App/code.exe",
                        "CODE.EXE",
                    ]
                }
            )

            reloaded = ConfigManager(
                str(root / "shortcuts.json"),
                str(root / "settings.json"),
            )
            reloaded.initialize_configs()

        self.assertEqual(
            reloaded.get_setting("excluded_applications"),
            ["CODE.EXE"],
        )


if __name__ == "__main__":
    unittest.main()
