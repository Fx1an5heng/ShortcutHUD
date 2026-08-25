"""Versioned, user-owned shortcut profile storage for ShortcutHUD."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import tempfile

from .modifier_state import normalize_modifier_combination
from .shortcut_key import normalize_shortcut_key
from .shortcut_resolver import (
    RESERVED_USER_IDENTITIES,
    normalize_application_identity,
)


SCHEMA_VERSION = 1
USER_CONFIG_ENV_VAR = "SHORTCUTHUD_USER_CONFIG_PATH"
LOAD_STATUS_NOT_LOADED = "not_loaded"
LOAD_STATUS_MISSING = "missing"
LOAD_STATUS_LOADED = "loaded"
LOAD_STATUS_ERROR = "error"
logger = logging.getLogger(__name__)


def resolve_user_config_path(
    explicit_path: str | os.PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve explicit, environment, then per-user APPDATA config paths."""

    if explicit_path is not None:
        return Path(explicit_path)

    environment = os.environ if environ is None else environ
    configured_path = environment.get(USER_CONFIG_ENV_VAR)
    if configured_path:
        return Path(configured_path)

    appdata = environment.get("APPDATA")
    roaming_root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return roaming_root / "ShortcutHUD" / "user_shortcuts.json"


def get_profile_display_names(
    profiles: Mapping[str, object],
) -> dict[str, str]:
    """Return normalized user display-name overrides in profile order."""

    display_names: dict[str, str] = {}
    for app_id, profile in profiles.items():
        if not isinstance(app_id, str) or not isinstance(profile, Mapping):
            continue
        normalized_id = normalize_application_identity(app_id)
        if normalized_id is None or normalized_id in RESERVED_USER_IDENTITIES:
            continue
        display_name = profile.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            display_names[normalized_id] = display_name.strip()
    return display_names


class UserShortcutStore:
    """Load, edit, and atomically save normalized user app profiles."""

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.path = resolve_user_config_path(path, environ)
        self._profiles: dict[str, dict[str, object]] = {}
        self.load_status = LOAD_STATUS_NOT_LOADED
        self.last_load_error: str | None = None

    def load(self) -> dict[str, dict[str, object]]:
        """Load a version-1 file; invalid whole files fail closed to empty."""

        if not self.path.exists():
            self._profiles = {}
            self.load_status = LOAD_STATUS_MISSING
            self.last_load_error = None
            return self.snapshot()

        try:
            with self.path.open("r", encoding="utf-8") as config_file:
                document = json.load(config_file)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            logger.warning("Ignoring invalid user shortcut file %s: %s", self.path, error)
            return self._fail_load(str(error))

        if not isinstance(document, Mapping):
            logger.warning("Ignoring user shortcut file with a non-object root: %s", self.path)
            return self._fail_load("user shortcut document root is not an object")
        version = document.get("version")
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != SCHEMA_VERSION
        ):
            logger.warning(
                "Ignoring unsupported user shortcut schema version in %s: %r",
                self.path,
                version,
            )
            return self._fail_load(f"unsupported schema version: {version!r}")

        apps = document.get("apps")
        if not isinstance(apps, Mapping):
            logger.warning("Ignoring user shortcut file with non-object apps: %s", self.path)
            return self._fail_load("user shortcut apps value is not an object")

        self._profiles = self._normalize_profiles(apps)
        self.load_status = LOAD_STATUS_LOADED
        self.last_load_error = None
        return self.snapshot()

    def reload(self) -> dict[str, dict[str, object]]:
        """Reload the configured path, replacing the current memory snapshot."""

        return self.load()

    def list_profiles(self) -> list[str]:
        return list(self._profiles)

    def get_profile(self, app_id: str) -> dict[str, object] | None:
        normalized_id = self._normalize_writable_identity(app_id)
        profile = self._profiles.get(normalized_id)
        return deepcopy(profile) if profile is not None else None

    def upsert_profile(
        self,
        app_id: str,
        display_name: str | None = None,
    ) -> dict[str, object]:
        normalized_id = self._normalize_writable_identity(app_id)
        profile = self._profiles.setdefault(normalized_id, {"shortcuts": {}})
        if display_name is not None:
            if not isinstance(display_name, str) or not display_name.strip():
                raise ValueError("display_name must be a non-empty string")
            profile["display_name"] = display_name.strip()
        return deepcopy(profile)

    def delete_profile(self, app_id: str) -> bool:
        normalized_id = self._normalize_writable_identity(app_id)
        return self._profiles.pop(normalized_id, None) is not None

    def set_shortcut(
        self,
        app_id: str,
        modifier: str,
        key: str,
        en: str,
        zh: str,
    ) -> None:
        normalized_id = self._normalize_writable_identity(app_id)
        canonical_modifier = self._normalize_writable_modifier(modifier)
        normalized_key = self._validate_key(key)
        description = self._validate_description({"en": en, "zh": zh})
        if description is None:
            raise ValueError("en and zh must both be strings")

        profile = self._profiles.setdefault(normalized_id, {"shortcuts": {}})
        shortcuts = profile.setdefault("shortcuts", {})
        assert isinstance(shortcuts, dict)
        modifier_group = shortcuts.setdefault(canonical_modifier, {})
        assert isinstance(modifier_group, dict)
        self._set_case_insensitive(modifier_group, normalized_key, description)

    def delete_shortcut(self, app_id: str, modifier: str, key: str) -> bool:
        normalized_id = self._normalize_writable_identity(app_id)
        canonical_modifier = self._normalize_writable_modifier(modifier)
        normalized_key = self._validate_key(key)
        profile = self._profiles.get(normalized_id)
        if profile is None:
            return False
        shortcuts = profile.get("shortcuts")
        if not isinstance(shortcuts, dict):
            return False
        modifier_group = shortcuts.get(canonical_modifier)
        if not isinstance(modifier_group, dict):
            return False

        stored_key = self._find_case_insensitive_key(modifier_group, normalized_key)
        if stored_key is None:
            return False
        del modifier_group[stored_key]
        if not modifier_group:
            del shortcuts[canonical_modifier]
        return True

    def save(self) -> None:
        """Persist UTF-8 JSON via same-directory fsync and atomic replace."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "version": SCHEMA_VERSION,
            "apps": self.snapshot(),
        }
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(document, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def snapshot(self) -> dict[str, dict[str, object]]:
        return deepcopy(self._profiles)

    def replace_snapshot(self, profiles: Mapping[str, object]) -> None:
        """Replace only the in-memory profiles with one normalized snapshot."""

        if not isinstance(profiles, Mapping):
            raise TypeError("profiles must be a mapping")
        self._profiles = self._normalize_profiles(profiles)

    def display_names_snapshot(self) -> dict[str, str]:
        return get_profile_display_names(self._profiles)

    def _fail_load(self, error: str) -> dict[str, dict[str, object]]:
        self._profiles = {}
        self.load_status = LOAD_STATUS_ERROR
        self.last_load_error = error
        return self.snapshot()

    @classmethod
    def _normalize_profiles(
        cls,
        apps: Mapping[object, object],
    ) -> dict[str, dict[str, object]]:
        normalized_profiles: dict[str, dict[str, object]] = {}
        for raw_app_id, raw_profile in apps.items():
            app_id = normalize_application_identity(raw_app_id)
            if app_id is None:
                logger.warning("Ignoring invalid user application identity: %r", raw_app_id)
                continue
            if app_id in RESERVED_USER_IDENTITIES:
                logger.warning("Ignoring reserved user application identity: %s", app_id)
                continue
            if not isinstance(raw_profile, Mapping):
                logger.warning("Ignoring non-object user profile: %s", app_id)
                continue

            normalized_profile = normalized_profiles.setdefault(
                app_id,
                {"shortcuts": {}},
            )
            raw_display_name = raw_profile.get("display_name")
            if raw_display_name is not None:
                if isinstance(raw_display_name, str) and raw_display_name.strip():
                    normalized_profile["display_name"] = raw_display_name.strip()
                else:
                    logger.warning("Ignoring invalid display_name for user profile: %s", app_id)

            raw_shortcuts = raw_profile.get("shortcuts", {})
            if not isinstance(raw_shortcuts, Mapping):
                logger.warning("Ignoring non-object shortcuts for user profile: %s", app_id)
                continue
            shortcuts = normalized_profile["shortcuts"]
            assert isinstance(shortcuts, dict)
            cls._merge_shortcut_groups(app_id, shortcuts, raw_shortcuts)
        return normalized_profiles

    @classmethod
    def _merge_shortcut_groups(
        cls,
        app_id: str,
        destination: dict[str, object],
        raw_shortcuts: Mapping[object, object],
    ) -> None:
        for raw_modifier, raw_group in raw_shortcuts.items():
            canonical_modifier = normalize_modifier_combination(raw_modifier)
            if canonical_modifier is None:
                logger.warning(
                    "Ignoring invalid user modifier for %s: %r",
                    app_id,
                    raw_modifier,
                )
                continue
            if not isinstance(raw_group, Mapping):
                logger.warning(
                    "Ignoring non-object shortcut group for %s %s",
                    app_id,
                    canonical_modifier,
                )
                continue

            group = destination.setdefault(canonical_modifier, {})
            assert isinstance(group, dict)
            for raw_key, raw_description in raw_group.items():
                try:
                    key = cls._validate_key(raw_key)
                except ValueError:
                    logger.warning(
                        "Ignoring invalid user shortcut key for %s %s: %r",
                        app_id,
                        canonical_modifier,
                        raw_key,
                    )
                    continue
                description = cls._validate_description(raw_description)
                if description is None:
                    logger.warning(
                        "Ignoring invalid user shortcut description for %s %s %s",
                        app_id,
                        canonical_modifier,
                        key,
                    )
                    continue
                cls._set_case_insensitive(group, key, description)

    @staticmethod
    def _normalize_writable_identity(app_id: str) -> str:
        normalized_id = normalize_application_identity(app_id)
        if normalized_id is None:
            raise ValueError("app_id must be a non-empty application identity")
        if normalized_id in RESERVED_USER_IDENTITIES:
            raise ValueError(f"reserved application identity: {normalized_id}")
        return normalized_id

    @staticmethod
    def _normalize_writable_modifier(modifier: str) -> str:
        canonical_modifier = normalize_modifier_combination(modifier)
        if canonical_modifier is None:
            raise ValueError("modifier must be a supported modifier combination")
        return canonical_modifier

    @staticmethod
    def _validate_key(key: object) -> str:
        return normalize_shortcut_key(key)

    @staticmethod
    def _validate_description(description: object) -> dict[str, str] | None:
        if not isinstance(description, Mapping):
            return None
        en = description.get("en")
        zh = description.get("zh")
        if not isinstance(en, str) or not isinstance(zh, str):
            return None
        return {"en": en, "zh": zh}

    @classmethod
    def _set_case_insensitive(
        cls,
        group: dict[str, object],
        key: str,
        description: dict[str, str],
    ) -> None:
        stored_key = cls._find_case_insensitive_key(group, key)
        group[stored_key if stored_key is not None else key] = description

    @staticmethod
    def _find_case_insensitive_key(
        group: Mapping[str, object],
        key: str,
    ) -> str | None:
        identity = key.casefold()
        return next(
            (stored_key for stored_key in group if stored_key.casefold() == identity),
            None,
        )
