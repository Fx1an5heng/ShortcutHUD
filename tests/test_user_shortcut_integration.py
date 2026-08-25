import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtWidgets import QApplication

from main import load_user_shortcut_store
from scripts.application_display_names import get_application_display_name
from scripts.shortcut_hud import ShortcutHudWindow, select_visible_entry_groups
from scripts.shortcut_hud_controller import ShortcutHudController
from scripts.shortcut_resolver import ShortcutEntry, resolve_shortcuts


class _Config:
    def __init__(self, shortcuts: dict[str, object]) -> None:
        self.shortcuts = shortcuts

    def get_all_shortcuts(self) -> dict[str, object]:
        return self.shortcuts

    def get_setting(self, _key: str, default: object = None) -> object:
        return default


class _Foreground:
    current_app_name = "CODE.EXE"
    identity_pending = False


class _Hud:
    def isVisible(self) -> bool:
        return False

    def hide(self) -> None:
        pass

    def show_hud(self) -> None:
        pass

    def set_entries(self, *_args: object) -> None:
        pass


class _Proxy:
    def current_physical_win_vk(self) -> int | None:
        return None

    def activate_for_current_hold(self, _win_vk: int) -> bool:
        return False


class UserShortcutIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    @staticmethod
    def _description(name: str) -> dict[str, str]:
        return {"en": name, "zh": name}

    def test_startup_loader_snapshot_reaches_real_resolver_and_hud_title(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "user_shortcuts.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "apps": {
                            "CODE.EXE": {
                                "display_name": "Custom VS Code",
                                "shortcuts": {
                                    "Ctrl": {
                                        "P": self._description("My Quick Open"),
                                        "F13": self._description("Custom Action"),
                                    }
                                },
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            store = load_user_shortcut_store(path)
            built_in = {
                "CODE.EXE": {
                    "Ctrl": {
                        "P": self._description("Built-in Quick Open"),
                        "B": self._description("Sidebar"),
                    }
                },
                "GLOBAL": {"Ctrl": {"G": self._description("Global")}},
            }

            entries = resolve_shortcuts(
                built_in,
                "CODE.EXE",
                "Ctrl",
                store.snapshot(),
            )
            hud = ShortcutHudWindow(
                application_display_names=store.display_names_snapshot()
            )
            hud.set_entries("CODE.EXE", "Ctrl", entries, "en_US")

            self.assertEqual(
                [(entry.key, entry.source) for entry in entries],
                [
                    ("P", "USER_APP"),
                    ("F13", "USER_APP"),
                    ("B", "APP"),
                    ("G", "GLOBAL"),
                ],
            )
            self.assertEqual(hud._header_label.text(), "Custom VS Code · Ctrl")
            hud.deleteLater()

    def test_controller_uses_injected_snapshot_and_can_update_it(self) -> None:
        built_in = {
            "CODE.EXE": {"Ctrl": {"P": "Built-in"}},
            "GLOBAL": {"Ctrl": {"G": "Global"}},
        }
        first = {
            "CODE.EXE": {"shortcuts": {"Ctrl": {"P": "First"}}}
        }
        controller = ShortcutHudController(
            _Config(built_in),
            _Foreground(),
            _Hud(),
            _Proxy(),
            user_profiles=first,
        )
        controller._current_modifier = "Ctrl"

        self.assertEqual(controller._resolve_current_entries()[0].description, "First")
        controller.update_user_profiles(
            {"CODE.EXE": {"shortcuts": {"Ctrl": {"P": "Second"}}}}
        )
        self.assertEqual(controller._resolve_current_entries()[0].description, "Second")
        controller.stop()

    def test_user_rows_are_extra_to_builtin_limit_and_global_is_pinned(self) -> None:
        entries = [
            ShortcutEntry(f"U{index}", f"User {index}", "USER_APP")
            for index in range(2)
        ] + [
            ShortcutEntry(f"A{index}", f"App {index}", "APP")
            for index in range(8)
        ] + [
            ShortcutEntry("Tab", "Switch", "GLOBAL"),
            ShortcutEntry("F4", "Close", "GLOBAL"),
        ]

        local, global_entries = select_visible_entry_groups(entries, 8)

        self.assertEqual(
            [entry.key for entry in local],
            [
                "U0",
                "U1",
                "A0",
                "A1",
                "A2",
                "A3",
                "A4",
                "A5",
                "A6",
                "A7",
            ],
        )
        self.assertEqual([entry.key for entry in global_entries], ["Tab", "F4"])

    def test_browser_ctrl_keeps_two_user_plus_nine_builtin_and_global(self) -> None:
        entries = [
            ShortcutEntry(f"U{index}", f"User {index}", "USER_APP")
            for index in range(2)
        ] + [
            ShortcutEntry(f"A{index}", f"App {index}", "APP")
            for index in range(9)
        ] + [ShortcutEntry("G", "Global", "GLOBAL")]
        hud = ShortcutHudWindow()

        hud.set_entries("MSEDGE.EXE", "Ctrl", entries, "en_US")

        local, global_entries = select_visible_entry_groups(entries, 9)
        self.assertEqual(len(local), 11)
        self.assertEqual([entry.key for entry in local[:2]], ["U0", "U1"])
        self.assertEqual([entry.key for entry in global_entries], ["G"])
        self.assertEqual(hud._entries_layout.count(), 13)
        hud.deleteLater()

    def test_user_display_name_priority_and_builtin_fallback(self) -> None:
        names = {
            "CODE.EXE": "我的 VS Code",
            "WPS_WRITER": "我的 WPS",
        }
        self.assertEqual(
            get_application_display_name("CODE.EXE", names),
            "我的 VS Code",
        )
        self.assertEqual(
            get_application_display_name("WPS_WRITER", names),
            "我的 WPS",
        )
        self.assertEqual(
            get_application_display_name("WPS_WRITER", {}),
            "WPS Writer",
        )
        self.assertEqual(
            get_application_display_name("CODE.EXE", {}),
            "CODE.EXE",
        )

    def test_reserved_identities_never_gain_an_application_label(self) -> None:
        malicious_names = {
            "WINDOWS_SHELL": "Desktop Local",
            "WPS_UNKNOWN": "Unknown WPS Local",
        }
        self.assertIsNone(
            get_application_display_name("WINDOWS_SHELL", malicious_names)
        )
        self.assertIsNone(
            get_application_display_name("WPS_UNKNOWN", malicious_names)
        )

    def test_user_global_collision_has_no_duplicate_global_section_entry(self) -> None:
        data = {
            "CODE.EXE": {"Alt": {"LEFT": "Back"}},
            "GLOBAL": {"Alt": {"Tab": "Switch", "F4": "Close"}},
        }
        users = {
            "CODE.EXE": {"shortcuts": {"Alt": {"f4": "My Close"}}}
        }

        entries = resolve_shortcuts(data, "CODE.EXE", "Alt", users)
        local, global_entries = select_visible_entry_groups(entries, 8)

        self.assertEqual(
            [(entry.key, entry.source) for entry in local],
            [("f4", "USER_APP"), ("LEFT", "APP")],
        )
        self.assertEqual(
            [(entry.key, entry.source) for entry in global_entries],
            [("Tab", "GLOBAL")],
        )


if __name__ == "__main__":
    unittest.main()
