"""Independent persisted Quick HUD entry selection for the future Catalog UI."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import tempfile

from .shortcut_resolver import normalize_application_identity

SCHEMA_VERSION = 1
SELECTION_CONFIG_ENV_VAR = "SHORTCUTHUD_QUICK_HUD_SELECTION_PATH"
logger = logging.getLogger(__name__)


def resolve_selection_config_path(path: str | os.PathLike[str] | None = None, environ: Mapping[str, str] | None = None) -> Path:
    if path is not None:
        return Path(path)
    environment = os.environ if environ is None else environ
    configured = environment.get(SELECTION_CONFIG_ENV_VAR)
    if configured:
        return Path(configured)
    appdata = environment.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "ShortcutHUD" / "quick_hud_selection.json"


class QuickHudSelectionStore:
    """Selections are distinct from built-in packs and legacy user shortcuts."""

    def __init__(self, path: str | os.PathLike[str] | None = None, *, environ: Mapping[str, str] | None = None) -> None:
        self.path = resolve_selection_config_path(path, environ)
        self._apps: dict[str, list[str]] = {}
        self.load_error: str | None = None

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(document, Mapping) or document.get("version") != SCHEMA_VERSION or not isinstance(document.get("apps"), Mapping):
                raise ValueError("invalid selection document")
            self._apps = self._normalize(document["apps"])
            self.load_error = None
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            self._apps = {}
            self.load_error = str(error)
            logger.warning("Ignoring invalid Quick HUD selection file %s: %s", self.path, error)

    def selected_ids_for(self, app_id: str | None) -> frozenset[str] | None:
        identity = normalize_application_identity(app_id)
        if identity is None or identity not in self._apps:
            return None
        return frozenset(self._apps[identity])

    def effective_selected_ids_for(
        self,
        app_id: str | None,
        entries: Iterable[object],
    ) -> frozenset[str] | None:
        """Resolve persisted IDs through declared stable aliases, never heuristics."""

        selected = self.selected_ids_for(app_id)
        if selected is None:
            return None
        resolved: set[str] = set()
        for entry in entries:
            entry_id = getattr(entry, "id", None)
            aliases = getattr(entry, "id_aliases", ())
            if not isinstance(entry_id, str):
                continue
            if entry_id in selected or (
                isinstance(aliases, tuple) and any(alias in selected for alias in aliases)
            ):
                resolved.add(entry_id)
        return frozenset(resolved)

    def set_selected_ids(self, app_id: str, entry_ids: Iterable[str]) -> None:
        identity = normalize_application_identity(app_id)
        if identity is None:
            raise ValueError("app_id is invalid")
        ids = list(entry_ids)
        if any(not isinstance(entry_id, str) or not entry_id.strip() for entry_id in ids) or len(set(ids)) != len(ids):
            raise ValueError("entry_ids must be unique non-empty strings")
        self._apps[identity] = ids

    def clear_selection(self, app_id: str) -> bool:
        identity = normalize_application_identity(app_id)
        return identity is not None and self._apps.pop(identity, None) is not None

    def snapshot(self) -> dict[str, list[str]]:
        return deepcopy(self._apps)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as file:
                temporary = Path(file.name)
                json.dump({"version": SCHEMA_VERSION, "apps": self.snapshot()}, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

    @staticmethod
    def _normalize(apps: Mapping[object, object]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for app, ids in apps.items():
            identity = normalize_application_identity(app)
            if identity is None or not isinstance(ids, list) or any(not isinstance(item, str) or not item.strip() for item in ids) or len(set(ids)) != len(ids):
                raise ValueError("invalid app selection")
            normalized[identity] = list(ids)
        return normalized
