import unittest
from types import SimpleNamespace

from main import ShortcutOverlayApplication


class _FakeHud:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self._events = events

    def update_application_display_names(self, display_names: object) -> None:
        self._events.append(("display_names", display_names))


class _FakeController:
    def __init__(self, events: list[tuple[str, object]]) -> None:
        self._events = events

    def update_user_profiles(self, snapshot: object) -> None:
        self._events.append(("profiles", snapshot))


class UserProfileRuntimeApplyTests(unittest.TestCase):
    def test_one_application_boundary_updates_labels_before_controller(self) -> None:
        events: list[tuple[str, object]] = []
        application = SimpleNamespace(
            shortcut_hud_window=_FakeHud(events),
            hud_controller=_FakeController(events),
        )
        snapshot = {
            "CODE.EXE": {
                "display_name": "My Code",
                "shortcuts": {},
            }
        }

        ShortcutOverlayApplication.apply_user_profiles(application, snapshot)

        self.assertEqual(
            events,
            [
                ("display_names", {"CODE.EXE": "My Code"}),
                ("profiles", snapshot),
            ],
        )
        self.assertIs(events[1][1], snapshot)


if __name__ == "__main__":
    unittest.main()
