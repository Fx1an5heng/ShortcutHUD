import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.shortcut_key import (
    InvalidShortcutKeyError,
    ModifierTerminalKeyError,
    UnsupportedShortcutSequenceError,
)
from scripts.user_shortcut_store import (
    LOAD_STATUS_ERROR,
    LOAD_STATUS_LOADED,
    LOAD_STATUS_MISSING,
    SCHEMA_VERSION,
    UserShortcutStore,
    resolve_user_config_path,
)


class UserShortcutStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.path = self.root / "nested" / "user_shortcuts.json"
        self.store = UserShortcutStore(self.path)

    def _write_document(self, document: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_missing_file_loads_empty_without_creating_anything(self) -> None:
        self.assertEqual(self.store.load(), {})
        self.assertEqual(self.store.load_status, LOAD_STATUS_MISSING)
        self.assertIsNone(self.store.last_load_error)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.parent.exists())

    def test_path_precedence_is_explicit_then_environment_then_appdata(self) -> None:
        environment = {
            "SHORTCUTHUD_USER_CONFIG_PATH": str(self.root / "environment.json"),
            "APPDATA": str(self.root / "roaming"),
        }
        self.assertEqual(
            resolve_user_config_path(self.root / "explicit.json", environment),
            self.root / "explicit.json",
        )
        self.assertEqual(
            resolve_user_config_path(environ=environment),
            self.root / "environment.json",
        )
        self.assertEqual(
            resolve_user_config_path(environ={"APPDATA": str(self.root / "roaming")}),
            self.root / "roaming" / "ShortcutHUD" / "user_shortcuts.json",
        )

    def test_valid_file_loads_and_normalizes_identity_modifier_and_order(self) -> None:
        self._write_document(
            {
                "version": 1,
                "apps": {
                    r"C:\Program Files\Microsoft VS Code\Code.exe": {
                        "display_name": "我的 VS Code",
                        "shortcuts": {
                            "Shift+Ctrl": {
                                "P": {"en": "Custom open", "zh": "自定义打开"},
                                "K": {"en": "Action K", "zh": "功能 K"},
                            }
                        },
                    }
                },
            }
        )

        profiles = self.store.load()

        self.assertEqual(self.store.load_status, LOAD_STATUS_LOADED)
        self.assertEqual(list(profiles), ["CODE.EXE"])
        profile = profiles["CODE.EXE"]
        self.assertEqual(profile["display_name"], "我的 VS Code")
        self.assertEqual(list(profile["shortcuts"]), ["Ctrl+Shift"])
        self.assertEqual(list(profile["shortcuts"]["Ctrl+Shift"]), ["P", "K"])

    def test_chinese_unicode_round_trip(self) -> None:
        self.store.upsert_profile("bilibili.exe", "哔哩哔哩")
        self.store.set_shortcut("bilibili.exe", "Alt", "F", "Fullscreen", "全屏")
        self.store.save()

        serialized = self.path.read_text(encoding="utf-8")
        reloaded = UserShortcutStore(self.path)
        reloaded.load()

        self.assertIn("哔哩哔哩", serialized)
        self.assertIn("全屏", serialized)
        self.assertEqual(reloaded.snapshot(), self.store.snapshot())

    def test_save_reload_is_semantically_identical(self) -> None:
        self.store.set_shortcut("TYPORA.EXE", "Ctrl", "K", "Link", "链接")
        expected = self.store.snapshot()
        self.store.save()

        self.store.delete_profile("TYPORA.EXE")
        self.assertEqual(self.store.reload(), expected)

    def test_parent_directory_is_created_only_by_first_save(self) -> None:
        self.store.upsert_profile("OBSIDIAN.EXE", "Obsidian")
        self.assertFalse(self.path.parent.exists())

        self.store.save()

        self.assertTrue(self.path.is_file())

    def test_atomic_save_writes_a_valid_versioned_target(self) -> None:
        self.store.set_shortcut("CODE.EXE", "Ctrl", "P", "Quick Open", "快速打开")
        self.store.save()

        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["version"], SCHEMA_VERSION)
        self.assertEqual(document["apps"], self.store.snapshot())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_failed_atomic_replace_preserves_old_valid_target(self) -> None:
        old_document = {"version": 1, "apps": {}}
        self._write_document(old_document)
        self.store.set_shortcut("CODE.EXE", "Ctrl", "P", "Quick Open", "快速打开")

        with patch("scripts.user_shortcut_store.os.replace", side_effect=OSError("fail")):
            with self.assertRaises(OSError):
                self.store.save()

        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")),
            old_document,
        )
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_malformed_json_fails_closed_without_overwriting_file(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{broken", encoding="utf-8")

        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            self.assertEqual(self.store.load(), {})

        self.assertEqual(self.store.load_status, LOAD_STATUS_ERROR)
        self.assertIsInstance(self.store.last_load_error, str)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")

    def test_invalid_utf8_fails_closed_without_changing_the_file(self) -> None:
        invalid_bytes = b'{"version": 1, "apps": {"CODE.EXE": "\xff\xfe\xfa"}}'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(invalid_bytes)

        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            snapshot = self.store.load()

        self.assertEqual(snapshot, {})
        self.assertEqual(self.store.load_status, LOAD_STATUS_ERROR)
        self.assertTrue(self.path.is_file())
        self.assertEqual(self.path.read_bytes(), invalid_bytes)
        self.assertEqual(
            [item for item in self.path.parent.iterdir() if item != self.path],
            [],
        )

    def test_unsupported_version_and_non_object_apps_fail_closed(self) -> None:
        for document in (
            {"version": 99, "apps": {}},
            {"version": True, "apps": {}},
            {"version": 1.0, "apps": {}},
            {"version": 1, "apps": []},
        ):
            with self.subTest(document=document):
                self._write_document(document)
                with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
                    self.assertEqual(self.store.load(), {})

    def test_reserved_identities_are_ignored_on_load_and_rejected_by_api(self) -> None:
        self._write_document(
            {
                "version": 2,
                "apps": {
                    "DEFAULT": {"shortcuts": {}, "hidden_builtin": {"Ctrl": ["H"]}},
                    "GLOBAL": {"shortcuts": {}, "hidden_builtin": {"Ctrl": ["H"]}},
                    "WINDOWS_SHELL": {"shortcuts": {}, "hidden_builtin": {"Ctrl": ["H"]}},
                    "WPS_UNKNOWN": {"shortcuts": {}, "hidden_builtin": {"Ctrl": ["H"]}},
                    "WPS_WRITER": {"shortcuts": {}, "hidden_builtin": {"Ctrl": ["H"]}},
                },
            }
        )

        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            profiles = self.store.load()

        self.assertEqual(list(profiles), ["WPS_WRITER"])
        self.assertEqual(
            profiles["WPS_WRITER"]["hidden_builtin"],
            {"Ctrl": ["H"]},
        )
        for identity in ("DEFAULT", "GLOBAL", "WINDOWS_SHELL", "WPS_UNKNOWN"):
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError):
                    self.store.upsert_profile(identity)

    def test_invalid_and_no_modifier_groups_are_ignored_independently(self) -> None:
        self._write_document(
            {
                "version": 1,
                "apps": {
                    "CODE.EXE": {
                        "shortcuts": {
                            "Ctrl+Hyper": {
                                "H": {"en": "Bad", "zh": "错误"}
                            },
                            "NoModifier": {
                                "N": {"en": "Bad", "zh": "错误"}
                            },
                            "Ctrl": {
                                "P": {"en": "Good", "zh": "正确"}
                            },
                        }
                    }
                },
            }
        )

        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            profiles = self.store.load()

        self.assertEqual(list(profiles["CODE.EXE"]["shortcuts"]), ["Ctrl"])

    def test_bad_profile_group_entry_and_description_do_not_drop_valid_data(self) -> None:
        self._write_document(
            {
                "version": 1,
                "apps": {
                    "CODE.EXE": {
                        "display_name": 123,
                        "shortcuts": {
                            "Alt": [],
                            "Ctrl": {
                                "P": {"en": "Good", "zh": "正确"},
                                "B": "not an object",
                                "C": {"en": 5, "zh": "错误"},
                            },
                        },
                    },
                },
            }
        )

        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            profiles = self.store.load()

        self.assertEqual(
            profiles,
            {
                "CODE.EXE": {
                    "shortcuts": {
                        "Ctrl": {"P": {"en": "Good", "zh": "正确"}}
                    }
                }
            },
        )

    def test_v1_load_is_read_only_and_explicit_save_upgrades_to_v2(self) -> None:
        self._write_document(
            {
                "version": 1,
                "apps": {
                    "CODE.EXE": {
                        "display_name": "My Code",
                        "shortcuts": {
                            "Ctrl": {
                                "P": {"en": "Open", "zh": "打开"},
                                "K": {"en": "Action", "zh": "操作"},
                            }
                        },
                    }
                },
            }
        )
        old_bytes = self.path.read_bytes()
        old_mtime = self.path.stat().st_mtime_ns

        snapshot = self.store.load()

        self.assertEqual(self.path.read_bytes(), old_bytes)
        self.assertEqual(self.path.stat().st_mtime_ns, old_mtime)
        self.assertEqual(list(snapshot["CODE.EXE"]["shortcuts"]["Ctrl"]), ["P", "K"])
        self.assertNotIn("hidden_builtin", snapshot["CODE.EXE"])

        self.store.save()
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["version"], 2)

    def test_failed_explicit_save_after_v1_load_preserves_original_v1_bytes(self) -> None:
        self._write_document(
            {
                "version": 1,
                "apps": {"CODE.EXE": {"shortcuts": {}}},
            }
        )
        old_bytes = self.path.read_bytes()
        self.store.load()
        self.store.hide_builtin_shortcut("CODE.EXE", "Ctrl", "H")

        with patch("scripts.user_shortcut_store.os.replace", side_effect=OSError("fail")):
            with self.assertRaises(OSError):
                self.store.save()

        self.assertEqual(self.path.read_bytes(), old_bytes)

    def test_v2_round_trip_preserves_user_hidden_and_insertion_order(self) -> None:
        self._write_document(
            {
                "version": 2,
                "apps": {
                    "code.exe": {
                        "display_name": "My Code",
                        "shortcuts": {
                            "Ctrl": {
                                "P": {"en": "Open", "zh": "打开"},
                                "K": {"en": "Action", "zh": "操作"},
                            }
                        },
                        "hidden_builtin": {
                            "shift+ctrl": ["p", "f4"],
                            "Alt": ["Enter"],
                        },
                    }
                },
            }
        )

        loaded = self.store.load()
        self.store.save()
        reloaded = UserShortcutStore(self.path)

        self.assertEqual(reloaded.load(), loaded)
        profile = loaded["CODE.EXE"]
        self.assertEqual(list(profile["shortcuts"]["Ctrl"]), ["P", "K"])
        self.assertEqual(
            profile["hidden_builtin"],
            {"Ctrl+Shift": ["P", "F4"], "Alt": ["Enter"]},
        )

    def test_v2_structural_corruption_fails_closed_and_preserves_bytes(self) -> None:
        documents = (
            {"version": 2, "apps": {"CODE.EXE": []}},
            {
                "version": 2,
                "apps": {"CODE.EXE": {"hidden_builtin": "bad"}},
            },
            {
                "version": 2,
                "apps": {
                    "CODE.EXE": {"hidden_builtin": {"Ctrl": {"bad": True}}}
                },
            },
        )
        for document in documents:
            with self.subTest(document=document):
                self._write_document(document)
                old_bytes = self.path.read_bytes()
                with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
                    self.assertEqual(self.store.load(), {})
                self.assertEqual(self.store.load_status, LOAD_STATUS_ERROR)
                self.assertEqual(self.path.read_bytes(), old_bytes)

    def test_v2_invalid_hidden_leaves_are_skipped_and_duplicates_deduplicate(self) -> None:
        self._write_document(
            {
                "version": 2,
                "apps": {
                    "CODE.EXE": {
                        "shortcuts": {
                            "Alt": {"Z": {"en": "User", "zh": "用户"}}
                        },
                        "hidden_builtin": {
                            "Ctrl": ["H", "F99", 5, "L", "f4", "F4"]
                        },
                    }
                },
            }
        )

        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            profiles = self.store.load()

        self.assertEqual(
            profiles["CODE.EXE"]["hidden_builtin"],
            {"Ctrl": ["H", "L", "F4"]},
        )
        self.assertIn("Z", profiles["CODE.EXE"]["shortcuts"]["Alt"])

    def test_suppression_api_is_canonical_idempotent_and_does_not_prune_profile(self) -> None:
        self.store.upsert_profile("CODE.EXE")

        self.assertTrue(self.store.hide_builtin_shortcut("code.exe", "ctrl", "f4"))
        self.assertFalse(self.store.hide_builtin_shortcut("CODE.EXE", "Ctrl", "F4"))
        self.assertTrue(self.store.hide_builtin_shortcut("CODE.EXE", "Ctrl", "h"))
        self.assertEqual(
            self.store.list_hidden_builtin_shortcuts("CODE.EXE"),
            [("Ctrl", "F4"), ("Ctrl", "H")],
        )
        self.assertTrue(self.store.is_builtin_hidden("CODE.EXE", "ctrl", "f4"))
        self.assertTrue(self.store.restore_builtin_shortcut("CODE.EXE", "Ctrl", "F4"))
        self.assertFalse(self.store.restore_builtin_shortcut("CODE.EXE", "Ctrl", "F4"))
        self.assertTrue(self.store.restore_all_hidden_builtins("CODE.EXE"))
        self.assertFalse(self.store.restore_all_hidden_builtins("CODE.EXE"))
        self.assertEqual(self.store.get_profile("CODE.EXE"), {"shortcuts": {}})

    def test_reserved_suppression_is_rejected_while_logical_wps_is_allowed(self) -> None:
        for identity in ("DEFAULT", "GLOBAL", "WINDOWS_SHELL", "WPS_UNKNOWN"):
            with self.subTest(identity=identity):
                with self.assertRaises(ValueError):
                    self.store.hide_builtin_shortcut(identity, "Ctrl", "H")

        for identity in ("WPS_WRITER", "WPS_PDF", "WPS_PRESENTATION"):
            with self.subTest(identity=identity):
                self.assertTrue(
                    self.store.hide_builtin_shortcut(identity, "Ctrl", "H")
                )

    def test_equivalent_modifier_groups_merge_in_first_position(self) -> None:
        self._write_document(
            {
                "version": 1,
                "apps": {
                    "CODE.EXE": {
                        "shortcuts": {
                            "Shift+Ctrl": {
                                "P": {"en": "First", "zh": "第一"}
                            },
                            "Ctrl+Shift": {
                                "K": {"en": "Second", "zh": "第二"}
                            },
                        }
                    }
                },
            }
        )

        profile = self.store.load()["CODE.EXE"]

        self.assertEqual(list(profile["shortcuts"]), ["Ctrl+Shift"])
        self.assertEqual(list(profile["shortcuts"]["Ctrl+Shift"]), ["P", "K"])

    def test_case_insensitive_set_updates_without_moving_or_duplicating_key(self) -> None:
        self.store.set_shortcut("CODE.EXE", "Ctrl", "F4", "First", "第一")
        self.store.set_shortcut("CODE.EXE", "Ctrl", "K", "Second", "第二")
        self.store.set_shortcut("code.exe", "ctrl", "f4", "Updated", "更新")

        group = self.store.get_profile("CODE.EXE")["shortcuts"]["Ctrl"]
        self.assertEqual(list(group), ["F4", "K"])
        self.assertEqual(group["F4"], {"en": "Updated", "zh": "更新"})

    def test_delete_shortcut_and_profile(self) -> None:
        self.store.set_shortcut("CODE.EXE", "Ctrl", "F4", "Close", "关闭")
        self.assertTrue(self.store.delete_shortcut("code.exe", "ctrl", "f4"))
        self.assertFalse(self.store.delete_shortcut("CODE.EXE", "Ctrl", "F4"))
        self.assertEqual(self.store.get_profile("CODE.EXE")["shortcuts"], {})
        self.assertTrue(self.store.delete_profile("code.exe"))
        self.assertFalse(self.store.delete_profile("code.exe"))

    def test_display_name_only_profile_persists_and_counts_as_a_profile(self) -> None:
        self.store.upsert_profile("BILIBILI.EXE", "哔哩哔哩")
        self.store.save()

        reloaded = UserShortcutStore(self.path)
        reloaded.load()

        self.assertEqual(reloaded.list_profiles(), ["BILIBILI.EXE"])
        self.assertEqual(
            reloaded.get_profile("BILIBILI.EXE"),
            {"display_name": "哔哩哔哩", "shortcuts": {}},
        )
        self.assertEqual(
            reloaded.display_names_snapshot(),
            {"BILIBILI.EXE": "哔哩哔哩"},
        )

    def test_replace_snapshot_normalizes_without_writing_to_disk(self) -> None:
        self.store.replace_snapshot(
            {
                "code.exe": {
                    "display_name": "My Code",
                    "shortcuts": {
                        "Shift+Ctrl": {
                            "P": {"en": "Open", "zh": "打开"},
                        }
                    },
                }
            }
        )

        self.assertEqual(
            self.store.snapshot(),
            {
                "CODE.EXE": {
                    "display_name": "My Code",
                    "shortcuts": {
                        "Ctrl+Shift": {
                            "P": {"en": "Open", "zh": "打开"},
                        }
                    },
                }
            },
        )
        self.assertFalse(self.path.exists())

    def test_set_shortcut_normalizes_key_and_preserves_position_on_update(self) -> None:
        self.store.set_shortcut("CODE.EXE", "Ctrl", "f4", "First", "第一")
        self.store.set_shortcut("CODE.EXE", "Ctrl", "K", "Second", "第二")
        self.store.set_shortcut("CODE.EXE", "Ctrl", "F4", "Updated", "更新")

        group = self.store.get_profile("CODE.EXE")["shortcuts"]["Ctrl"]
        self.assertEqual(list(group), ["F4", "K"])
        self.assertEqual(group["F4"], {"en": "Updated", "zh": "更新"})

    def test_set_shortcut_rejects_invalid_modifier_and_multistep_terminal_keys(self) -> None:
        invalid_keys = (
            "",
            "   ",
            "F0",
            "F25",
            "F99",
            "HELLO",
            "ABC",
            "CtrlP",
            "Ctrl+P",
            "NotAKey",
        )
        for key in invalid_keys:
            with self.subTest(key=key):
                with self.assertRaises(InvalidShortcutKeyError):
                    self.store.set_shortcut("CODE.EXE", "Ctrl", key, "Bad", "错误")

        modifier_terminal_cases = (
            ("Ctrl", "Ctrl"),
            ("Ctrl", "Control"),
            ("Ctrl", "Alt"),
            ("Ctrl", "Shift"),
            ("Ctrl+Shift", "Shift"),
            ("Alt", "Ctrl"),
            ("Ctrl", "Win"),
            ("Ctrl", "Windows"),
        )
        for modifier, key in modifier_terminal_cases:
            with self.subTest(modifier=modifier, key=key):
                with self.assertRaises(ModifierTerminalKeyError):
                    self.store.set_shortcut(
                        "CODE.EXE", modifier, key, "Bad", "错误"
                    )

        for key in (
            "Ctrl+W, W",
            "Ctrl+K Ctrl+S",
            "Ctrl+K, Ctrl+S",
            "g g",
            "d d",
            "dd",
        ):
            with self.subTest(key=key):
                with self.assertRaises(UnsupportedShortcutSequenceError):
                    self.store.set_shortcut("CODE.EXE", "Ctrl", key, "Chord", "多段")

        self.assertEqual(self.store.snapshot(), {})

    def test_set_shortcut_accepts_combined_modifier_with_terminal_key(self) -> None:
        self.store.set_shortcut(
            "CODE.EXE", "Ctrl+Shift", "P", "Open", "打开"
        )
        self.store.set_shortcut(
            "CODE.EXE", "Ctrl+Alt", "F5", "Refresh", "刷新"
        )

        groups = self.store.get_profile("CODE.EXE")["shortcuts"]
        self.assertEqual(list(groups["Ctrl+Shift"]), ["P"])
        self.assertEqual(list(groups["Ctrl+Alt"]), ["F5"])

    def test_mixed_valid_and_invalid_external_keys_load_independently(self) -> None:
        self._write_document(
            {
                "version": 1,
                "apps": {
                    "CODE.EXE": {
                        "shortcuts": {
                            "Ctrl": {
                                "f13": {"en": "Macro", "zh": "宏键"},
                                "F99": {"en": "Bad", "zh": "错误"},
                                "enter": {"en": "Line", "zh": "换行"},
                            }
                        }
                    },
                    "OTHER.EXE": {
                        "shortcuts": {
                            "Alt": {
                                "z": {"en": "Other", "zh": "其它"},
                            }
                        }
                    },
                },
            }
        )

        with self.assertLogs("scripts.user_shortcut_store", level="WARNING"):
            profiles = self.store.load()

        self.assertEqual(
            list(profiles["CODE.EXE"]["shortcuts"]["Ctrl"]),
            ["F13", "Enter"],
        )
        self.assertEqual(
            list(profiles["OTHER.EXE"]["shortcuts"]["Alt"]),
            ["Z"],
        )


if __name__ == "__main__":
    unittest.main()
