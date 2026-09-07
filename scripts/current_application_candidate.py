"""Track the latest external, resolver-facing application identity."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import replace

import win32process
from PySide6.QtCore import QObject, Signal, Slot

from .application_descriptor import ApplicationDescriptor, ApplicationDescriptorFactory
from .shell_identity import WINDOWS_DESKTOP
from .shortcut_resolver import (
    RESERVED_USER_IDENTITIES,
    normalize_application_identity,
)


def _get_window_process_id(hwnd: int) -> int | None:
    if hwnd <= 0:
        return None
    try:
        _thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return None
    return int(process_id) if process_id else None


class CurrentApplicationCandidateTracker(QObject):
    """Remember the final app identity while excluding this process by HWND PID."""

    candidate_changed = Signal(object)
    foreground_context_changed = Signal(object)

    def __init__(
        self,
        hwnd_provider: Callable[[], int],
        parent: QObject | None = None,
        *,
        process_id_provider: Callable[[int], int | None] = _get_window_process_id,
        own_process_id: int | None = None,
        executable_path_provider: Callable[[], str | None] | None = None,
        descriptor_factory: ApplicationDescriptorFactory | None = None,
    ) -> None:
        super().__init__(parent)
        self._hwnd_provider = hwnd_provider
        self._process_id_provider = process_id_provider
        self._own_process_id = os.getpid() if own_process_id is None else own_process_id
        self._candidate: str | None = None
        self._recent_candidates: list[str] = []
        self._current_descriptor: ApplicationDescriptor | None = None
        self._actual_context: ApplicationDescriptor | None = None
        self._recent_descriptors: list[ApplicationDescriptor] = []
        self._executable_path_provider = executable_path_provider or (lambda: None)
        self._descriptor_factory = descriptor_factory or ApplicationDescriptorFactory()
        self._detection_order = 0

    @property
    def current_candidate(self) -> str | None:
        """Return the latest external identity, including reserved identities."""

        return self._candidate

    def editable_candidate(self) -> str | None:
        """Return a candidate that may be used as a USER profile identity."""

        if self._candidate in RESERVED_USER_IDENTITIES:
            return None
        return self._candidate

    @property
    def recent_candidates(self) -> tuple[str, ...]:
        """Most recently observed external identities, newest first."""

        return tuple(self._recent_candidates)

    @property
    def current_descriptor(self) -> ApplicationDescriptor | None:
        """Last valid external application, kept for ShortcutHUD self fallback."""

        return self._current_descriptor

    @property
    def last_external_descriptor(self) -> ApplicationDescriptor | None:
        return self._current_descriptor

    @property
    def actual_context(self) -> ApplicationDescriptor | None:
        """The real foreground context; this may be desktop or ShortcutHUD itself."""

        return self._actual_context

    @property
    def center_context(self) -> ApplicationDescriptor | None:
        """Use actual external/desktop context, otherwise the self-window fallback."""

        if self._actual_context is not None and self._actual_context.context_kind != "self":
            return self._actual_context
        return self._current_descriptor

    @property
    def recent_descriptors(self) -> tuple[ApplicationDescriptor, ...]:
        """Session-only external application history, newest first."""

        return tuple(self._recent_descriptors)

    @Slot(str)
    def on_active_app_changed(self, application_identity: str) -> None:
        """Accept a final runtime identity unless its HWND belongs to this process."""

        try:
            hwnd = int(self._hwnd_provider() or 0)
        except (TypeError, ValueError, OSError):
            return
        try:
            process_id = self._process_id_provider(hwnd)
        except (OSError, TypeError, ValueError):
            return
        normalized_identity = normalize_application_identity(application_identity)
        if process_id is None:
            return
        if process_id == self._own_process_id:
            self._set_actual_context(self._self_context(normalized_identity))
            return
        if normalized_identity == WINDOWS_DESKTOP:
            self._detection_order += 1
            self._set_actual_context(
                self._descriptor_factory.describe(normalized_identity, order=self._detection_order)
            )
            return
        if normalized_identity is None or normalized_identity in RESERVED_USER_IDENTITIES:
            self._set_actual_context(None)
            return
        if normalized_identity == self._candidate:
            self._set_actual_context(self._current_descriptor)
            return
        self._candidate = normalized_identity
        if normalized_identity is not None:
            if normalized_identity in self._recent_candidates:
                self._recent_candidates.remove(normalized_identity)
            self._recent_candidates.insert(0, normalized_identity)
            del self._recent_candidates[8:]
            try:
                executable_path = self._executable_path_provider()
            except (OSError, TypeError, ValueError):
                executable_path = None
            self._detection_order += 1
            descriptor = self._descriptor_factory.describe(
                normalized_identity,
                executable_path,
                order=self._detection_order,
            )
            self._current_descriptor = descriptor
            if descriptor is not None:
                self._recent_descriptors = [
                    item
                    for item in self._recent_descriptors
                    if item.runtime_identity != descriptor.runtime_identity
                ]
                self._recent_descriptors.insert(0, descriptor)
                del self._recent_descriptors[8:]
            self._set_actual_context(descriptor)
        self.candidate_changed.emit(self._candidate)

    def _set_actual_context(self, descriptor: ApplicationDescriptor | None) -> None:
        if descriptor == self._actual_context:
            return
        self._actual_context = descriptor
        self.foreground_context_changed.emit(descriptor)

    def _self_context(self, identity: str | None) -> ApplicationDescriptor | None:
        if identity is None:
            return None
        descriptor = self._descriptor_factory.describe(identity)
        if descriptor is None:
            return None
        return replace(descriptor, context_kind="self")
