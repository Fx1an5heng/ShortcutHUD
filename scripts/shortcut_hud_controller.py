"""Modifier-to-resolver orchestration for the compact ShortcutHUD window."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Protocol

from PySide6.QtCore import QObject, QTimer, Slot

from .modifier_state import canonicalize_modifier_state
from .shortcut_resolver import ShortcutEntry, resolve_shortcuts


class _ConfigProvider(Protocol):
    def get_all_shortcuts(self) -> dict[str, object]: ...

    def get_setting(self, key: str, default: object = None) -> object: ...


class _ForegroundState(Protocol):
    current_app_name: str | None
    identity_pending: bool


class _HudView(Protocol):
    def isVisible(self) -> bool: ...

    def hide(self) -> None: ...

    def show_hud(self) -> None: ...

    def set_entries(
        self,
        application_name: str,
        modifier_combination: str,
        entries: list[ShortcutEntry],
        language: str | None,
    ) -> None: ...


class _WinDiscoveryProxy(Protocol):
    def current_physical_win_vk(self) -> int | None: ...

    def activate_for_current_hold(self, win_vk: int) -> bool: ...


class ShortcutHudController(QObject):
    """Resolve modifier state and update one persistent HUD view."""

    DEFAULT_SHOW_DELAY_MS = 150
    WIN_ONLY_SHOW_DELAY_MS = 300
    _MODIFIER_KEY_NAMES = frozenset({"ctrl", "alt", "shift", "win"})

    def __init__(
        self,
        config_manager: _ConfigProvider,
        foreground_monitor: _ForegroundState,
        hud_window: _HudView,
        win_discovery_proxy: _WinDiscoveryProxy,
        parent: QObject | None = None,
        show_delay_ms: int = DEFAULT_SHOW_DELAY_MS,
        win_only_show_delay_ms: int = WIN_ONLY_SHOW_DELAY_MS,
        user_profiles: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_manager = config_manager
        self._foreground_monitor = foreground_monitor
        self._hud_window = hud_window
        self._win_discovery_proxy = win_discovery_proxy
        self._user_profiles: dict[str, object] = (
            deepcopy(dict(user_profiles))
            if isinstance(user_profiles, Mapping)
            else {}
        )
        self._current_modifier: str | None = None
        self._show_delay_ms = show_delay_ms
        self._win_only_show_delay_ms = win_only_show_delay_ms
        self._identity_delay_elapsed = False

        self._win_modifier_held = False
        self._win_activation_attempted = False
        self._win_discovery_active = False
        self._win_execution_seen = False

        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._show_pending_hud)

    @Slot(set)
    def on_modifiers_changed(self, modifiers: set[str]) -> None:
        """Schedule, update, or hide the HUD for the latest logical state."""

        self._identity_delay_elapsed = False
        win_held = self._contains_win_modifier(modifiers)
        if win_held and not self._win_modifier_held:
            self._reset_win_discovery_state()
        elif not win_held:
            self._reset_win_discovery_state()
        self._win_modifier_held = win_held

        self._current_modifier = canonicalize_modifier_state(modifiers)
        self.refresh_current_state()

    @Slot(str, str)
    def on_key_event(self, key_name: str, event_type: str) -> None:
        """Hide an active Win discovery HUD once real shortcut execution starts."""

        if (
            not self._win_discovery_active
            or not isinstance(key_name, str)
            or not isinstance(event_type, str)
            or event_type.casefold() != "down"
            or key_name.casefold() in self._MODIFIER_KEY_NAMES
        ):
            return

        self._win_execution_seen = True
        self._cancel_and_hide()

    @Slot(str)
    def on_active_app_changed(self, _application_name: str) -> None:
        """Refresh from ForegroundMonitor's already-maintained current state."""

        if self._current_modifier is not None:
            self.refresh_current_state()

    def refresh_current_state(self) -> None:
        """Re-resolve the latest state without querying foreground Windows."""

        if self._current_modifier is None:
            self._cancel_and_hide()
            return

        entries = self._resolve_current_entries()
        if not entries:
            if self._is_identity_pending():
                self._hud_window.hide()
                if (
                    not self._show_timer.isActive()
                    and not self._identity_delay_elapsed
                ):
                    self._start_show_timer()
                return
            self._cancel_and_hide()
            return

        if self._win_discovery_active and self._win_execution_seen:
            self._cancel_and_hide()
            return
        if self._identity_delay_elapsed:
            self._identity_delay_elapsed = False
            self._show_pending_hud()
            return


        if self._current_modifier == "Win" and not self._win_discovery_active:
            self._show_timer.stop()
            self._hud_window.hide()
            if not self._win_activation_attempted:
                self._start_show_timer()
            return

        if self._hud_window.isVisible():
            self._show_timer.stop()
            self._render(entries)
            return

        self._start_show_timer()

    def stop(self) -> None:
        """Clear controller work; the application owns the proxy lifecycle."""

        self._current_modifier = None
        self._win_modifier_held = False
        self._reset_win_discovery_state()
        self._cancel_and_hide()

    def update_user_profiles(self, profiles: Mapping[str, object] | None) -> None:
        """Replace the in-memory USER_APP snapshot for a future editor reload."""

        self._user_profiles = (
            deepcopy(dict(profiles)) if isinstance(profiles, Mapping) else {}
        )
        self.refresh_current_state()

    def _show_pending_hud(self) -> None:
        if self._current_modifier is None:
            return

        entries = self._resolve_current_entries()
        if not entries:
            self._hud_window.hide()
            if self._is_identity_pending():
                self._identity_delay_elapsed = True
            else:
                self._identity_delay_elapsed = False
            return

        if self._current_modifier == "Win":
            if self._win_activation_attempted or self._win_execution_seen:
                self._hud_window.hide()
                return
            self._win_activation_attempted = True

            win_vk = self._current_physical_win_vk()
            if win_vk is None or not self._activate_win_proxy(win_vk):
                self._hud_window.hide()
                return
            self._win_discovery_active = True

        self._identity_delay_elapsed = False
        self._render(entries)
        self._hud_window.show_hud()

    def _resolve_current_entries(self) -> list[ShortcutEntry]:
        return resolve_shortcuts(
            self._config_manager.get_all_shortcuts(),
            self._foreground_monitor.current_app_name,
            self._current_modifier,
            self._user_profiles,
        )

    def _render(self, entries: list[ShortcutEntry]) -> None:
        app_name = self._foreground_monitor.current_app_name
        language_setting = self._config_manager.get_setting("language", "en_US")
        language = language_setting if isinstance(language_setting, str) else "en_US"
        self._hud_window.set_entries(
            app_name.upper() if app_name else "DEFAULT",
            self._current_modifier or "",
            entries,
            language,
        )

    def _cancel_and_hide(self) -> None:
        self._show_timer.stop()
        self._hud_window.hide()

        self._identity_delay_elapsed = False

    def _start_show_timer(self) -> None:
        if self._show_timer.isActive():
            return
        delay = (
            self._win_only_show_delay_ms
            if self._current_modifier == "Win"
            else self._show_delay_ms
        )
        self._show_timer.setInterval(delay)
        self._show_timer.start()

    def _is_identity_pending(self) -> bool:
        return bool(getattr(self._foreground_monitor, "identity_pending", False))

    def _current_physical_win_vk(self) -> int | None:
        try:
            return self._win_discovery_proxy.current_physical_win_vk()
        except Exception:
            return None

    def _activate_win_proxy(self, win_vk: int) -> bool:
        try:
            return self._win_discovery_proxy.activate_for_current_hold(win_vk)
        except Exception:
            return False

    def _reset_win_discovery_state(self) -> None:
        self._win_activation_attempted = False
        self._win_discovery_active = False
        self._win_execution_seen = False

    @staticmethod
    def _contains_win_modifier(modifiers: set[str]) -> bool:
        return any(
            isinstance(modifier, str) and modifier.casefold() == "win"
            for modifier in modifiers
        )
