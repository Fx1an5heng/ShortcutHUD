"""Runtime coordination for fullscreen and excluded-application suppression."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from PySide6.QtCore import QObject, Signal, Slot

from .game_guard_settings import (
    DEFAULT_FULLSCREEN_SUPPRESSION_ENABLED,
    EXCLUDED_APPLICATIONS_SETTING,
    FULLSCREEN_SUPPRESSION_SETTING,
    normalize_excluded_application,
    normalize_excluded_applications,
)
from .suppression_policy import SuppressionPolicy


class _FullscreenDetector(Protocol):
    def is_fullscreen(self, hwnd: object) -> bool: ...


class GameGuardRuntime(QObject):
    """Translate current context into independent suppression-policy sources."""

    suppression_changed = Signal()

    def __init__(
        self,
        policy: SuppressionPolicy,
        fullscreen_detector: _FullscreenDetector,
        application_identity_provider: Callable[[], str | None],
        settings: Mapping[str, object] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._policy = policy
        self._fullscreen_detector = fullscreen_detector
        self._application_identity_provider = application_identity_provider
        self._current_hwnd = 0
        self._current_application_id: str | None = None
        self._fullscreen_suppression_enabled = (
            DEFAULT_FULLSCREEN_SUPPRESSION_ENABLED
        )
        self._excluded_applications: frozenset[str] = frozenset()
        self._fullscreen_active = False
        self._excluded_app_active = False
        self.update_settings(settings or {})

    @property
    def fullscreen_suppression_enabled(self) -> bool:
        return self._fullscreen_suppression_enabled

    @property
    def excluded_applications(self) -> frozenset[str]:
        return self._excluded_applications

    @property
    def fullscreen_active(self) -> bool:
        return self._fullscreen_active

    @property
    def excluded_app_active(self) -> bool:
        return self._excluded_app_active

    def update_settings(self, settings: Mapping[str, object]) -> None:
        """Apply persistent settings and immediately re-evaluate current context."""

        enabled = settings.get(
            FULLSCREEN_SUPPRESSION_SETTING,
            DEFAULT_FULLSCREEN_SUPPRESSION_ENABLED,
        )
        self._fullscreen_suppression_enabled = (
            enabled
            if isinstance(enabled, bool)
            else DEFAULT_FULLSCREEN_SUPPRESSION_ENABLED
        )
        self._excluded_applications = frozenset(
            normalize_excluded_applications(
                settings.get(EXCLUDED_APPLICATIONS_SETTING, [])
            )
        )
        self._evaluate_current_context(read_fullscreen=True)

    def set_manual_game_mode(self, enabled: bool) -> None:
        """Update the session-only hard-block source through the same notifier."""

        previous_decision = self._policy.decision
        self._policy.set_manual_game_mode(enabled)
        self._emit_if_effective_decision_changed(previous_decision)

    @Slot(object, object)
    def on_foreground_polled(
        self,
        hwnd: object,
        _executable_name: object,
    ) -> None:
        """Reconcile runtime sources on every existing foreground-monitor tick."""

        try:
            self._current_hwnd = int(hwnd or 0)
        except (TypeError, ValueError, OverflowError):
            self._current_hwnd = 0
        self._current_application_id = self._read_application_identity()
        self._evaluate_current_context(read_fullscreen=True)

    @Slot(str)
    def on_active_app_changed(self, application_name: str) -> None:
        """Refresh exclusion immediately when the final logical identity changes."""

        self._current_application_id = normalize_excluded_application(
            application_name
        )
        self._evaluate_current_context(read_fullscreen=False)

    def _evaluate_current_context(self, *, read_fullscreen: bool) -> None:
        if read_fullscreen:
            self._fullscreen_active = bool(
                self._current_hwnd > 0
                and self._fullscreen_suppression_enabled
                and self._fullscreen_detector.is_fullscreen(self._current_hwnd)
            )

        self._excluded_app_active = bool(
            self._current_hwnd > 0
            and self._current_application_id in self._excluded_applications
        )
        previous_decision = self._policy.decision
        self._policy.set_runtime_sources(
            fullscreen_active=self._fullscreen_active,
            excluded_app_active=self._excluded_app_active,
        )
        self._emit_if_effective_decision_changed(previous_decision)

    def _read_application_identity(self) -> str | None:
        try:
            value = self._application_identity_provider()
        except BaseException:
            return None
        return normalize_excluded_application(value)

    def _emit_if_effective_decision_changed(self, previous_decision: object) -> None:
        if self._policy.decision is not previous_decision:
            self.suppression_changed.emit()
