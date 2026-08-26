"""Detached USER profile editor for ShortcutHUD."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from itertools import combinations
from typing import Protocol

from PySide6.QtCore import QEvent, QTimer, Qt, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .application_display_names import get_application_display_name
from .modifier_state import CANONICAL_MODIFIER_ORDER, normalize_modifier_combination
from .shortcut_key import (
    ModifierTerminalKeyError,
    ShortcutKeyError,
    UnsupportedShortcutSequenceError,
    normalize_builtin_shortcut_identity,
    normalize_shortcut_key,
)
from .shortcut_resolver import (
    RESERVED_USER_IDENTITIES,
    normalize_application_identity,
)
from .shortcut_description import select_description_text
from .shortcut_recorder import (
    RecordingRejection,
    RecordingState,
    ShortcutRecorder,
)
from .user_shortcut_store import LOAD_STATUS_ERROR, UserShortcutStore


class _CandidateTracker(Protocol):
    candidate_changed: object

    @property
    def current_candidate(self) -> str | None: ...

    def editable_candidate(self) -> str | None: ...


class ProfileValidationError(ValueError):
    """A user-editable profile value violates the Phase 5A schema contract."""


def supported_modifier_combinations() -> tuple[str, ...]:
    """Return every non-empty logical modifier combination in canonical order."""

    return tuple(
        "+".join(group)
        for size in range(1, len(CANONICAL_MODIFIER_ORDER) + 1)
        for group in combinations(CANONICAL_MODIFIER_ORDER, size)
    )


class UserProfileDraft:
    """Detached, ordered USER profile state; mutations never touch disk or runtime."""

    def __init__(self, profiles: Mapping[str, object] | None = None) -> None:
        self._profiles: dict[str, dict[str, object]] = deepcopy(
            dict(profiles) if isinstance(profiles, Mapping) else {}
        )
        self._original = deepcopy(self._profiles)

    @property
    def dirty(self) -> bool:
        return self._profiles != self._original

    def mark_saved(self) -> None:
        self._original = deepcopy(self._profiles)

    def snapshot(self) -> dict[str, dict[str, object]]:
        return deepcopy(self._profiles)

    def list_profiles(self) -> list[str]:
        return list(self._profiles)

    def get_profile(self, app_id: str) -> dict[str, object] | None:
        normalized_id = self._normalize_app_id(app_id)
        profile = self._profiles.get(normalized_id)
        return deepcopy(profile) if profile is not None else None

    def add_profile(self, app_id: str) -> bool:
        normalized_id = self._normalize_app_id(app_id)
        if normalized_id in self._profiles:
            return False
        self._profiles[normalized_id] = {"shortcuts": {}}
        return True

    def delete_profile(self, app_id: str) -> bool:
        normalized_id = self._normalize_app_id(app_id)
        return self._profiles.pop(normalized_id, None) is not None

    def set_display_name(self, app_id: str, display_name: str) -> None:
        profile = self._require_profile(app_id)
        normalized_name = display_name.strip()
        if normalized_name:
            profile["display_name"] = normalized_name
        else:
            profile.pop("display_name", None)

    def list_shortcuts(
        self,
        app_id: str,
    ) -> list[tuple[str, str, dict[str, str]]]:
        profile = self._require_profile(app_id)
        shortcuts = profile.get("shortcuts", {})
        if not isinstance(shortcuts, Mapping):
            return []
        return [
            (modifier, key, deepcopy(description))
            for modifier, group in shortcuts.items()
            if isinstance(modifier, str) and isinstance(group, Mapping)
            for key, description in group.items()
            if isinstance(key, str) and isinstance(description, dict)
        ]

    def add_shortcut(
        self,
        app_id: str,
        modifier: str,
        key: str,
        zh: str,
        en: str,
    ) -> None:
        canonical, normalized_key, description = self._validate_shortcut(
            modifier, key, zh, en
        )
        shortcuts = self._shortcuts_for(app_id)
        group = shortcuts.setdefault(canonical, {})
        assert isinstance(group, dict)
        if self._find_key(group, normalized_key) is not None:
            raise ProfileValidationError(
                "This modifier and key already exist in the user profile."
            )
        group[normalized_key] = description

    def edit_shortcut(
        self,
        app_id: str,
        old_modifier: str,
        old_key: str,
        modifier: str,
        key: str,
        zh: str,
        en: str,
    ) -> None:
        old_canonical = self._normalize_modifier(old_modifier)
        canonical, normalized_key, description = self._validate_shortcut(
            modifier, key, zh, en
        )
        shortcuts = self._shortcuts_for(app_id)
        old_group = shortcuts.get(old_canonical)
        if not isinstance(old_group, dict):
            raise ProfileValidationError("The shortcut being edited no longer exists.")
        stored_old_key = self._find_key(old_group, old_key)
        if stored_old_key is None:
            raise ProfileValidationError("The shortcut being edited no longer exists.")

        target_group = shortcuts.get(canonical)
        if isinstance(target_group, Mapping):
            duplicate = self._find_key(target_group, normalized_key)
            if duplicate is not None and not (
                canonical == old_canonical and duplicate == stored_old_key
            ):
                raise ProfileValidationError(
                    "This modifier and key already exist in the user profile."
                )

        if canonical == old_canonical:
            replacement: dict[str, object] = {}
            for stored_key, stored_description in old_group.items():
                if stored_key == stored_old_key:
                    replacement[normalized_key] = description
                else:
                    replacement[stored_key] = stored_description
            shortcuts[canonical] = replacement
            return

        del old_group[stored_old_key]
        if not old_group:
            del shortcuts[old_canonical]
        new_group = shortcuts.setdefault(canonical, {})
        assert isinstance(new_group, dict)
        new_group[normalized_key] = description

    def delete_shortcut(self, app_id: str, modifier: str, key: str) -> bool:
        canonical = self._normalize_modifier(modifier)
        shortcuts = self._shortcuts_for(app_id)
        group = shortcuts.get(canonical)
        if not isinstance(group, dict):
            return False
        stored_key = self._find_key(group, key)
        if stored_key is None:
            return False
        del group[stored_key]
        if not group:
            del shortcuts[canonical]
        return True

    def move_shortcut(
        self,
        app_id: str,
        modifier: str,
        key: str,
        offset: int,
    ) -> bool:
        if offset not in (-1, 1):
            raise ValueError("offset must be -1 or 1")
        canonical = self._normalize_modifier(modifier)
        shortcuts = self._shortcuts_for(app_id)
        group = shortcuts.get(canonical)
        if not isinstance(group, dict):
            return False
        stored_key = self._find_key(group, key)
        if stored_key is None:
            return False
        items = list(group.items())
        index = next(i for i, item in enumerate(items) if item[0] == stored_key)
        target = index + offset
        if target < 0 or target >= len(items):
            return False
        items[index], items[target] = items[target], items[index]
        shortcuts[canonical] = dict(items)
        return True

    def hide_builtin_shortcut(
        self,
        app_id: str,
        modifier: str,
        key: str,
    ) -> bool:
        canonical, normalized_key = self._validate_builtin_identity(modifier, key)
        hidden = self._hidden_builtins_for(app_id)
        group = hidden.setdefault(canonical, [])
        assert isinstance(group, list)
        if self._find_list_key(group, normalized_key) is not None:
            return False
        group.append(normalized_key)
        return True

    def restore_builtin_shortcut(
        self,
        app_id: str,
        modifier: str,
        key: str,
    ) -> bool:
        canonical, normalized_key = self._validate_builtin_identity(modifier, key)
        profile = self._require_profile(app_id)
        hidden = profile.get("hidden_builtin")
        if not isinstance(hidden, dict):
            return False
        group = hidden.get(canonical)
        if not isinstance(group, list):
            return False
        stored_key = self._find_list_key(group, normalized_key)
        if stored_key is None:
            return False
        group.remove(stored_key)
        if not group:
            del hidden[canonical]
        if not hidden:
            profile.pop("hidden_builtin", None)
        return True

    def restore_all_hidden_builtins(self, app_id: str) -> bool:
        profile = self._require_profile(app_id)
        hidden = profile.get("hidden_builtin")
        if not isinstance(hidden, Mapping) or not hidden:
            return False
        profile.pop("hidden_builtin", None)
        return True

    def is_builtin_hidden(self, app_id: str, modifier: str, key: str) -> bool:
        canonical, normalized_key = self._validate_builtin_identity(modifier, key)
        profile = self._require_profile(app_id)
        hidden = profile.get("hidden_builtin")
        group = hidden.get(canonical) if isinstance(hidden, Mapping) else None
        return isinstance(group, list) and (
            self._find_list_key(group, normalized_key) is not None
        )

    def list_hidden_builtin_shortcuts(
        self,
        app_id: str,
    ) -> list[tuple[str, str]]:
        profile = self._require_profile(app_id)
        hidden = profile.get("hidden_builtin")
        if not isinstance(hidden, Mapping):
            return []
        return [
            (modifier, key)
            for modifier, group in hidden.items()
            if isinstance(modifier, str) and isinstance(group, list)
            for key in group
            if isinstance(key, str)
        ]

    def validate_all(self) -> None:
        for app_id, profile in self._profiles.items():
            if self._normalize_app_id(app_id) != app_id:
                raise ProfileValidationError(f"Invalid application ID: {app_id}")
            if not isinstance(profile, Mapping):
                raise ProfileValidationError(f"Invalid profile: {app_id}")
            display_name = profile.get("display_name")
            if display_name is not None and (
                not isinstance(display_name, str) or not display_name.strip()
            ):
                raise ProfileValidationError(f"Invalid display name: {app_id}")
            shortcuts = profile.get("shortcuts", {})
            if not isinstance(shortcuts, Mapping):
                raise ProfileValidationError(f"Invalid shortcuts: {app_id}")
            for modifier, group in shortcuts.items():
                canonical = self._normalize_modifier(modifier)
                if canonical != modifier or not isinstance(group, Mapping):
                    raise ProfileValidationError(
                        f"Invalid modifier group: {app_id} {modifier}"
                    )
                seen: set[str] = set()
                for key, description in group.items():
                    _canonical, normalized_key, normalized_description = (
                        self._validate_shortcut(
                            modifier,
                            key,
                            description.get("zh") if isinstance(description, Mapping) else None,
                            description.get("en") if isinstance(description, Mapping) else None,
                        )
                    )
                    identity = normalized_key.casefold()
                    if identity in seen:
                        raise ProfileValidationError(
                            f"Duplicate shortcut: {app_id} {modifier} {key}"
                        )
                    seen.add(identity)
                    if normalized_description != description:
                        raise ProfileValidationError(
                            f"Invalid description: {app_id} {modifier} {key}"
                        )
            hidden = profile.get("hidden_builtin")
            if hidden is None:
                continue
            if not isinstance(hidden, Mapping):
                raise ProfileValidationError(f"Invalid hidden shortcuts: {app_id}")
            for modifier, group in hidden.items():
                canonical = self._normalize_modifier(modifier)
                if canonical != modifier or not isinstance(group, list):
                    raise ProfileValidationError(
                        f"Invalid hidden modifier group: {app_id} {modifier}"
                    )
                seen_hidden: set[str] = set()
                for key in group:
                    normalized_modifier, normalized_key = (
                        self._validate_builtin_identity(modifier, key)
                    )
                    if normalized_modifier != modifier or normalized_key != key:
                        raise ProfileValidationError(
                            f"Invalid hidden shortcut: {app_id} {modifier} {key}"
                        )
                    identity = normalized_key.casefold()
                    if identity in seen_hidden:
                        raise ProfileValidationError(
                            f"Duplicate hidden shortcut: {app_id} {modifier} {key}"
                        )
                    seen_hidden.add(identity)

    @staticmethod
    def _normalize_app_id(app_id: str) -> str:
        normalized_id = normalize_application_identity(app_id)
        if normalized_id is None:
            raise ProfileValidationError("Application ID must not be empty.")
        if normalized_id in RESERVED_USER_IDENTITIES:
            raise ProfileValidationError(
                "The current window is not a customizable application."
            )
        return normalized_id

    @staticmethod
    def _normalize_modifier(modifier: str) -> str:
        canonical = normalize_modifier_combination(modifier)
        if canonical is None:
            raise ProfileValidationError("Select a supported modifier combination.")
        return canonical

    @classmethod
    def _validate_shortcut(
        cls,
        modifier: str,
        key: object,
        zh: object,
        en: object,
    ) -> tuple[str, str, dict[str, str]]:
        canonical = cls._normalize_modifier(modifier)
        try:
            normalized_key = normalize_shortcut_key(key)
        except ShortcutKeyError as error:
            raise ProfileValidationError(str(error)) from error
        if not isinstance(zh, str) or not zh.strip():
            raise ProfileValidationError("Chinese description must not be empty.")
        if not isinstance(en, str) or not en.strip():
            raise ProfileValidationError("English description must not be empty.")
        return canonical, normalized_key, {"en": en.strip(), "zh": zh.strip()}

    def _require_profile(self, app_id: str) -> dict[str, object]:
        normalized_id = self._normalize_app_id(app_id)
        profile = self._profiles.get(normalized_id)
        if profile is None:
            raise ProfileValidationError(f"Unknown user profile: {normalized_id}")
        return profile

    def _shortcuts_for(self, app_id: str) -> dict[str, object]:
        profile = self._require_profile(app_id)
        shortcuts = profile.setdefault("shortcuts", {})
        if not isinstance(shortcuts, dict):
            raise ProfileValidationError("Profile shortcuts are invalid.")
        return shortcuts

    def _hidden_builtins_for(self, app_id: str) -> dict[str, object]:
        profile = self._require_profile(app_id)
        hidden = profile.setdefault("hidden_builtin", {})
        if not isinstance(hidden, dict):
            raise ProfileValidationError("Profile hidden shortcuts are invalid.")
        return hidden

    @staticmethod
    def _validate_builtin_identity(
        modifier: object,
        key: object,
    ) -> tuple[str, str]:
        try:
            return normalize_builtin_shortcut_identity(modifier, key)
        except ValueError as error:
            raise ProfileValidationError(str(error)) from error

    @staticmethod
    def _find_key(group: Mapping[str, object], key: str) -> str | None:
        identity = key.casefold()
        return next(
            (stored_key for stored_key in group if stored_key.casefold() == identity),
            None,
        )

    @staticmethod
    def _find_list_key(group: list[str], key: str) -> str | None:
        identity = key.casefold()
        return next((stored_key for stored_key in group if stored_key.casefold() == identity), None)


class ShortcutEditDialog(QDialog):
    """Small editor for one opaque shortcut key and bilingual description."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        modifier: str = "Ctrl",
        key: str = "",
        zh: str = "",
        en: str = "",
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle(self.tr("Shortcut"))
        self._recorder = ShortcutRecorder()
        self._recording_targets: list[QWidget] = []
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.modifier_combo = QComboBox(self)
        self.modifier_combo.addItems(supported_modifier_combinations())
        index = self.modifier_combo.findText(modifier)
        self.modifier_combo.setCurrentIndex(max(index, 0))
        self.key_edit = QLineEdit(key, self)
        self.zh_edit = QLineEdit(zh, self)
        self.en_edit = QLineEdit(en, self)
        form.addRow(self.tr("Modifier:"), self.modifier_combo)
        form.addRow(self.tr("Key:"), self.key_edit)
        form.addRow(self.tr("Chinese:"), self.zh_edit)
        form.addRow(self.tr("English:"), self.en_edit)
        layout.addLayout(form)

        self.record_button = QPushButton(self.tr("Record Shortcut"), self)
        self.record_button.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_button)
        self.recording_hint_label = QLabel(self)
        self.recording_hint_label.setWordWrap(True)
        layout.addWidget(self.recording_hint_label)
        self._set_recording_hint()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def recording_state(self) -> RecordingState:
        """Expose the local recorder state for UI tests and diagnostics."""

        return self._recorder.state

    def _set_recording_hint(self, message: str | None = None) -> None:
        self.recording_hint_label.setText(
            message
            if message is not None
            else self.tr(
                "Press a shortcut.\n"
                "This version automatically records single-step shortcuts "
                "with Ctrl, Alt, or Shift.\n"
                "Win, system-reserved, and multi-step shortcuts must be "
                "entered manually."
            )
        )

    @Slot()
    def _toggle_recording(self) -> None:
        if self._recorder.state is RecordingState.RECORDING:
            self.cancel_recording()
        else:
            self.start_recording()

    @Slot()
    def start_recording(self) -> bool:
        if not self._recorder.start():
            return False
        self._install_recording_filters()
        self.record_button.setText(self.tr("Cancel Recording"))
        self._set_recording_hint(self.tr("Recording...\nPress a shortcut."))
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    @Slot()
    def cancel_recording(self) -> bool:
        if self._recorder.state is not RecordingState.RECORDING:
            return False
        self._stop_recording()
        return True

    def _install_recording_filters(self) -> None:
        self._remove_recording_filters()
        targets = [self, *self.findChildren(QWidget)]
        for widget in targets:
            widget.installEventFilter(self)
        self._recording_targets = targets

    def _remove_recording_filters(self) -> None:
        for widget in self._recording_targets:
            widget.removeEventFilter(self)
        self._recording_targets.clear()

    def _stop_recording(self, hint: str | None = None) -> None:
        self._remove_recording_filters()
        self._recorder.cancel()
        self.record_button.setText(self.tr("Record Shortcut"))
        self._set_recording_hint(hint)

    def _cancel_if_focus_lost(self) -> None:
        if self._recorder.state is not RecordingState.RECORDING:
            return
        focus_widget = QApplication.focusWidget()
        if focus_widget is None:
            self._stop_recording(
                self.tr("Recording cancelled because the dialog lost focus.")
            )
            return
        inside_dialog = focus_widget is self or self.isAncestorOf(focus_widget)
        if not inside_dialog or (self.isVisible() and not self.isActiveWindow()):
            self._stop_recording(
                self.tr("Recording cancelled because the dialog lost focus.")
            )

    def _show_recording_rejection(self, rejection: RecordingRejection) -> None:
        messages = {
            RecordingRejection.NO_MODIFIER: self.tr(
                "A modifier key is required in this version."
            ),
            RecordingRejection.WIN: self.tr(
                "Win shortcuts are not recorded automatically yet. "
                "Please enter them manually."
            ),
            RecordingRejection.ALTGR: self.tr(
                "This shortcut cannot be recorded safely. Please enter it "
                "manually."
            ),
            RecordingRejection.CTRL_ALT_PRINTABLE: self.tr(
                "This Ctrl+Alt printable shortcut may be AltGr. Please enter "
                "it manually."
            ),
            RecordingRejection.UNSUPPORTED_KEY: self.tr(
                "This shortcut cannot be recorded safely. Please enter it "
                "manually."
            ),
        }
        self._set_recording_hint(messages[rejection])

    def _apply_recorded_shortcut(self, modifier: str, key: str) -> None:
        self._stop_recording()
        self.modifier_combo.blockSignals(True)
        self.key_edit.blockSignals(True)
        try:
            index = self.modifier_combo.findText(modifier)
            if index >= 0:
                self.modifier_combo.setCurrentIndex(index)
            self.key_edit.setText(key)
        finally:
            self.key_edit.blockSignals(False)
            self.modifier_combo.blockSignals(False)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched not in self._recording_targets:
            return super().eventFilter(watched, event)
        if event.type() in (QEvent.Type.FocusOut, QEvent.Type.WindowDeactivate):
            QTimer.singleShot(0, self._cancel_if_focus_lost)
            return False
        if self._recorder.state is not RecordingState.RECORDING:
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False

        result = self._recorder.handle_event(event)
        if result is not None:
            if result.shortcut is not None:
                self._apply_recorded_shortcut(*result.shortcut)
            elif result.rejection is not None:
                self._show_recording_rejection(result.rejection)
        return True

    def reject(self) -> None:
        self._stop_recording()
        super().reject()

    def accept(self) -> None:
        self._stop_recording()
        super().accept()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_recording()
        super().closeEvent(event)

    def values(self) -> tuple[str, str, str, str]:
        return (
            self.modifier_combo.currentText(),
            normalize_shortcut_key(self.key_edit.text()),
            self.zh_edit.text(),
            self.en_edit.text(),
        )

    @Slot()
    def _validate_and_accept(self) -> None:
        try:
            normalize_shortcut_key(self.key_edit.text())
        except ShortcutKeyError as error:
            self._show_key_validation_error(error)
            return
        self.accept()

    def _show_key_validation_error(self, error: ShortcutKeyError) -> None:
        if isinstance(error, UnsupportedShortcutSequenceError):
            message = self.tr(
                "Only single-step shortcuts are supported in this version.\n"
                "Multi-step/chord shortcuts will be supported in a future version."
            )
        elif isinstance(error, ModifierTerminalKeyError):
            combined_modifier = normalize_modifier_combination(
                f"{self.modifier_combo.currentText()}+{error.modifier}"
            ) or self.modifier_combo.currentText()
            message = self.tr(
                "{key} is a modifier key. Select {modifier} in Modifier and "
                "enter the action key in Key."
            ).format(
                key=error.modifier,
                modifier=combined_modifier,
            )
        else:
            message = self.tr(
                "Enter a valid keyboard key. For Chinese full-width punctuation, "
                "use the corresponding half-width keyboard symbol."
            )
        QMessageBox.warning(self, self.tr("Shortcut"), message)


class UserShortcutManagerDialog(QDialog):
    """Edit a complete detached USER snapshot and apply it after durable save."""

    def __init__(
        self,
        live_store: UserShortcutStore,
        candidate_tracker: _CandidateTracker,
        apply_user_profiles: Callable[[Mapping[str, object]], None],
        builtin_shortcuts: Mapping[str, object] | None = None,
        language: str | None = "en",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Shortcut Manager"))
        self.resize(900, 560)
        self._live_store = live_store
        self._candidate_tracker = candidate_tracker
        self._apply_user_profiles = apply_user_profiles
        self._builtin_shortcuts = deepcopy(
            dict(builtin_shortcuts) if isinstance(builtin_shortcuts, Mapping) else {}
        )
        self._language = language
        self._draft = UserProfileDraft(live_store.snapshot())
        self._current_app_id: str | None = None
        self._editing_blocked = live_store.load_status == LOAD_STATUS_ERROR

        root = QVBoxLayout(self)
        self.corrupt_config_label = QLabel(self)
        self.corrupt_config_label.setWordWrap(True)
        self.corrupt_config_label.setStyleSheet("color: #ffcc66;")
        self.corrupt_config_label.setText(
            self.tr(
                "The user configuration file cannot be read. Editing and saving "
                "are disabled to protect the original file."
            )
            if self._editing_blocked
            else ""
        )
        self.corrupt_config_label.setVisible(self._editing_blocked)
        root.addWidget(self.corrupt_config_label)

        self.candidate_label = QLabel(self)
        root.addWidget(self.candidate_label)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(splitter, 1)

        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel(self.tr("User Profiles"), left))
        self.profile_list = QListWidget(left)
        self.profile_list.setObjectName("userProfileList")
        left_layout.addWidget(self.profile_list, 1)
        self.add_current_button = QPushButton(self.tr("Add Current App"), left)
        self.delete_profile_button = QPushButton(self.tr("Delete App"), left)
        left_layout.addWidget(self.add_current_button)
        left_layout.addWidget(self.delete_profile_button)

        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        profile_form = QFormLayout()
        self.application_id_label = QLabel("—", right)
        self.application_id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.display_name_edit = QLineEdit(right)
        profile_form.addRow(self.tr("Application ID:"), self.application_id_label)
        profile_form.addRow(self.tr("Display Name:"), self.display_name_edit)
        right_layout.addLayout(profile_form)

        self.tabs = QTabWidget(right)
        right_layout.addWidget(self.tabs, 1)

        custom_tab = QWidget(self.tabs)
        custom_layout = QVBoxLayout(custom_tab)
        self.tabs.addTab(custom_tab, self.tr("Custom Shortcuts"))

        self.shortcut_table = QTableWidget(0, 4, custom_tab)
        self.shortcut_table.setHorizontalHeaderLabels(
            [
                self.tr("Modifier"),
                self.tr("Key"),
                self.tr("Chinese"),
                self.tr("English"),
            ]
        )
        self.shortcut_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.shortcut_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.shortcut_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.shortcut_table.horizontalHeader().setStretchLastSection(True)
        custom_layout.addWidget(self.shortcut_table, 1)

        actions = QHBoxLayout()
        self.add_shortcut_button = QPushButton(self.tr("Add"), custom_tab)
        self.edit_shortcut_button = QPushButton(self.tr("Edit"), custom_tab)
        self.delete_shortcut_button = QPushButton(self.tr("Delete"), custom_tab)
        self.move_up_button = QPushButton(self.tr("Move Up"), custom_tab)
        self.move_down_button = QPushButton(self.tr("Move Down"), custom_tab)
        for button in (
            self.add_shortcut_button,
            self.edit_shortcut_button,
            self.delete_shortcut_button,
            self.move_up_button,
            self.move_down_button,
        ):
            actions.addWidget(button)
        custom_layout.addLayout(actions)
        self.builtin_note = QLabel(
            self.tr("Built-in shortcuts not shown here remain available."), custom_tab
        )
        self.builtin_note.setWordWrap(True)
        custom_layout.addWidget(self.builtin_note)

        builtin_tab = QWidget(self.tabs)
        builtin_layout = QVBoxLayout(builtin_tab)
        self.tabs.addTab(builtin_tab, self.tr("Built-in Shortcuts"))
        self.builtin_table = QTableWidget(0, 4, builtin_tab)
        self.builtin_table.setHorizontalHeaderLabels(
            [
                self.tr("Modifier"),
                self.tr("Key"),
                self.tr("Description"),
                self.tr("Status"),
            ]
        )
        self.builtin_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.builtin_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.builtin_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.builtin_table.horizontalHeader().setStretchLastSection(True)
        builtin_layout.addWidget(self.builtin_table, 1)
        builtin_actions = QHBoxLayout()
        self.hide_restore_builtin_button = QPushButton(
            self.tr("Hide Built-in Shortcut"),
            builtin_tab,
        )
        self.restore_all_builtins_button = QPushButton(
            self.tr("Restore All Hidden Built-in Shortcuts"),
            builtin_tab,
        )
        builtin_actions.addWidget(self.hide_restore_builtin_button)
        builtin_actions.addWidget(self.restore_all_builtins_button)
        builtin_layout.addLayout(builtin_actions)
        self.builtin_scope_note = QLabel(
            self.tr(
                "Only the app-specific built-in hint is hidden. "
                "Global shortcuts are unaffected."
            ),
            builtin_tab,
        )
        self.builtin_scope_note.setWordWrap(True)
        builtin_layout.addWidget(self.builtin_scope_note)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([250, 650])

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        root.addWidget(self.button_box)

        self.profile_list.currentItemChanged.connect(self._on_profile_selected)
        self.display_name_edit.textChanged.connect(self._on_display_name_changed)
        self.add_current_button.clicked.connect(self.add_current_application)
        self.delete_profile_button.clicked.connect(self.delete_selected_profile)
        self.add_shortcut_button.clicked.connect(self.add_shortcut)
        self.edit_shortcut_button.clicked.connect(self.edit_selected_shortcut)
        self.delete_shortcut_button.clicked.connect(self.delete_selected_shortcut)
        self.move_up_button.clicked.connect(lambda: self.move_selected_shortcut(-1))
        self.move_down_button.clicked.connect(lambda: self.move_selected_shortcut(1))
        self.builtin_table.itemSelectionChanged.connect(
            self._update_builtin_action_state
        )
        self.hide_restore_builtin_button.clicked.connect(
            self.toggle_selected_builtin
        )
        self.restore_all_builtins_button.clicked.connect(
            self.restore_all_hidden_builtins
        )
        self.button_box.accepted.connect(self.save_changes)
        self.button_box.rejected.connect(self.reject)
        candidate_signal = getattr(candidate_tracker, "candidate_changed", None)
        if candidate_signal is not None and hasattr(candidate_signal, "connect"):
            candidate_signal.connect(self._on_candidate_changed)

        self._reload_profile_list()
        self._update_candidate_label()
        self._update_enabled_state()

    @property
    def draft(self) -> UserProfileDraft:
        return self._draft

    @Slot()
    def add_current_application(self) -> bool:
        candidate = self._candidate_tracker.editable_candidate()
        if candidate is None:
            self._show_warning(
                self.tr("The current window is not a customizable application.")
            )
            return False
        try:
            self._draft.add_profile(candidate)
        except ProfileValidationError as error:
            self._show_profile_validation_error(error)
            return False
        self._reload_profile_list(select_app_id=candidate)
        return True

    @Slot()
    def delete_selected_profile(self) -> bool:
        if self._current_app_id is None:
            return False
        if not self._confirm(
            self.tr(
                "Deleting this custom app profile also removes its custom shortcuts, "
                "custom display name, and hidden built-in shortcut records.\n\n"
                "Hidden built-in shortcuts may appear again. Delete this profile?"
            )
        ):
            return False
        deleted = self._draft.delete_profile(self._current_app_id)
        self._current_app_id = None
        self._reload_profile_list()
        return deleted

    @Slot()
    def add_shortcut(self) -> bool:
        if self._current_app_id is None:
            return False
        editor = ShortcutEditDialog(self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            self._draft.add_shortcut(self._current_app_id, *editor.values())
        except ProfileValidationError as error:
            self._show_profile_validation_error(error)
            return False
        self._render_shortcuts()
        return True

    @Slot()
    def edit_selected_shortcut(self) -> bool:
        selected = self._selected_shortcut()
        if self._current_app_id is None or selected is None:
            return False
        modifier, key, zh, en = selected
        editor = ShortcutEditDialog(
            self,
            modifier=modifier,
            key=key,
            zh=zh,
            en=en,
        )
        if editor.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            self._draft.edit_shortcut(
                self._current_app_id,
                modifier,
                key,
                *editor.values(),
            )
        except ProfileValidationError as error:
            self._show_profile_validation_error(error)
            return False
        self._render_shortcuts()
        return True

    @Slot()
    def delete_selected_shortcut(self) -> bool:
        selected = self._selected_shortcut()
        if self._current_app_id is None or selected is None:
            return False
        deleted = self._draft.delete_shortcut(
            self._current_app_id, selected[0], selected[1]
        )
        self._render_shortcuts()
        return deleted

    def move_selected_shortcut(self, offset: int) -> bool:
        selected = self._selected_shortcut()
        if self._current_app_id is None or selected is None:
            return False
        moved = self._draft.move_shortcut(
            self._current_app_id, selected[0], selected[1], offset
        )
        self._render_shortcuts(select_identity=(selected[0], selected[1]))
        return moved

    @Slot()
    def toggle_selected_builtin(self) -> bool:
        if self._current_app_id is None:
            return False
        identity = self._selected_builtin_identity()
        if identity is None:
            self._show_warning(
                self.tr(
                    "This shortcut type cannot be hidden in this version."
                )
            )
            return False
        modifier, key = identity
        if self._draft.is_builtin_hidden(self._current_app_id, modifier, key):
            changed = self._draft.restore_builtin_shortcut(
                self._current_app_id,
                modifier,
                key,
            )
        else:
            changed = self._draft.hide_builtin_shortcut(
                self._current_app_id,
                modifier,
                key,
            )
        self._render_builtin_shortcuts(select_identity=identity)
        return changed

    @Slot()
    def restore_all_hidden_builtins(self) -> bool:
        if self._current_app_id is None:
            return False
        if not self._draft.list_hidden_builtin_shortcuts(self._current_app_id):
            return False
        if not self._confirm(
            self.tr(
                "Restore all hidden built-in shortcuts for this app?\n\n"
                "Custom shortcuts and the display name will not be changed."
            )
        ):
            return False
        changed = self._draft.restore_all_hidden_builtins(self._current_app_id)
        self._render_builtin_shortcuts()
        return changed

    @Slot()
    def save_changes(self) -> bool:
        if self._editing_blocked:
            self._show_warning(
                self.tr("Saving is disabled because the user configuration is invalid.")
            )
            return False
        try:
            self._draft.validate_all()
            snapshot = self._draft.snapshot()
            transaction_store = UserShortcutStore(self._live_store.path)
            transaction_store.replace_snapshot(snapshot)
            transaction_store.save()
        except (OSError, ProfileValidationError, TypeError, ValueError) as error:
            self._show_save_error(error)
            return False

        durable_snapshot = transaction_store.snapshot()
        self._live_store.replace_snapshot(durable_snapshot)
        self._apply_user_profiles(durable_snapshot)
        self._draft.mark_saved()
        self.accept()
        return True

    def reject(self) -> None:
        if self._draft.dirty and not self._confirm(
            self.tr("There are unsaved changes. Discard them?")
        ):
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._draft.dirty and not self._confirm(
            self.tr("There are unsaved changes. Discard them?")
        ):
            event.ignore()
            return
        # QDialog.closeEvent() rejects the dialog. Marking this detached draft as
        # acknowledged prevents the reject path from asking the same question twice.
        self._draft.mark_saved()
        super().closeEvent(event)

    @Slot(object)
    def _on_candidate_changed(self, _candidate: object) -> None:
        self._update_candidate_label()

    @Slot(object, object)
    def _on_profile_selected(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        self._current_app_id = (
            current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        )
        profile = (
            self._draft.get_profile(self._current_app_id)
            if self._current_app_id
            else None
        )
        self.application_id_label.setText(self._current_app_id or "—")
        self.display_name_edit.blockSignals(True)
        self.display_name_edit.setText(
            str(profile.get("display_name", "")) if profile else ""
        )
        self.display_name_edit.blockSignals(False)
        self._render_shortcuts()
        self._update_enabled_state()

    @Slot(str)
    def _on_display_name_changed(self, display_name: str) -> None:
        if self._current_app_id is None:
            return
        self._draft.set_display_name(self._current_app_id, display_name)
        current_item = self.profile_list.currentItem()
        if current_item is not None:
            current_item.setText(self._profile_label(self._current_app_id))

    def _reload_profile_list(self, select_app_id: str | None = None) -> None:
        selected = select_app_id or self._current_app_id
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        selected_item: QListWidgetItem | None = None
        for app_id in self._draft.list_profiles():
            item = QListWidgetItem(self._profile_label(app_id), self.profile_list)
            item.setData(Qt.ItemDataRole.UserRole, app_id)
            item.setToolTip(app_id)
            if app_id == selected:
                selected_item = item
        self.profile_list.blockSignals(False)
        if selected_item is not None:
            self.profile_list.setCurrentItem(selected_item)
        elif self.profile_list.count():
            self.profile_list.setCurrentRow(0)
        else:
            self._on_profile_selected(None, None)

    def _profile_label(self, app_id: str) -> str:
        profile = self._draft.get_profile(app_id) or {}
        display_name = profile.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            display_name = get_application_display_name(app_id)
        return str(display_name or app_id)

    def _render_shortcuts(
        self,
        select_identity: tuple[str, str] | None = None,
    ) -> None:
        entries = (
            self._draft.list_shortcuts(self._current_app_id)
            if self._current_app_id
            else []
        )
        self.shortcut_table.setRowCount(0)
        selected_row = -1
        for row, (modifier, key, description) in enumerate(entries):
            self.shortcut_table.insertRow(row)
            values = (modifier, key, description["zh"], description["en"])
            for column, value in enumerate(values):
                self.shortcut_table.setItem(row, column, QTableWidgetItem(value))
            if select_identity == (modifier, key):
                selected_row = row
        if selected_row >= 0:
            self.shortcut_table.selectRow(selected_row)
        self._render_builtin_shortcuts()

    def _render_builtin_shortcuts(
        self,
        select_identity: tuple[str, str] | None = None,
    ) -> None:
        self.builtin_table.setRowCount(0)
        selected_row = -1
        for row, (
            modifier,
            key,
            description,
            identity,
        ) in enumerate(self._list_builtin_rows()):
            hidden = False
            overridden = False
            if self._current_app_id is not None and identity is not None:
                hidden = self._draft.is_builtin_hidden(
                    self._current_app_id,
                    identity[0],
                    identity[1],
                )
                overridden = self._has_user_shortcut(identity)

            if identity is None:
                status = self.tr("Unsupported shortcut type")
            elif hidden and overridden:
                status = self.tr("Hidden and Overridden")
            elif hidden:
                status = self.tr("Hidden")
            elif overridden:
                status = self.tr("Overridden by Custom Shortcut")
            else:
                status = self.tr("Visible")

            self.builtin_table.insertRow(row)
            values = (modifier, key, description, status)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, identity)
                if identity is None:
                    item.setToolTip(
                        self.tr(
                            "This shortcut type cannot be hidden in this version."
                        )
                    )
                self.builtin_table.setItem(row, column, item)
            if identity is not None and select_identity == identity:
                selected_row = row
        if selected_row >= 0:
            self.builtin_table.selectRow(selected_row)
        self._update_builtin_action_state()

    def _list_builtin_rows(
        self,
    ) -> list[tuple[str, str, str, tuple[str, str] | None]]:
        layer = self._find_builtin_layer(self._current_app_id)
        if layer is None:
            return []
        rows: list[tuple[str, str, str, tuple[str, str] | None]] = []
        for raw_modifier, group in layer.items():
            if not isinstance(raw_modifier, str) or not isinstance(group, Mapping):
                continue
            for raw_key, raw_description in group.items():
                if not isinstance(raw_key, str):
                    continue
                identity: tuple[str, str] | None
                try:
                    identity = normalize_builtin_shortcut_identity(
                        raw_modifier,
                        raw_key,
                    )
                except ValueError:
                    identity = None
                description = select_description_text(
                    raw_description,
                    self._language,
                )
                rows.append((raw_modifier, raw_key, description, identity))
        return rows

    def _find_builtin_layer(
        self,
        app_id: str | None,
    ) -> Mapping[str, object] | None:
        normalized_id = normalize_application_identity(app_id)
        if normalized_id is None:
            return None
        for configured_id, layer in self._builtin_shortcuts.items():
            if (
                normalize_application_identity(configured_id) == normalized_id
                and isinstance(layer, Mapping)
            ):
                return layer
        return None

    def _has_user_shortcut(self, identity: tuple[str, str]) -> bool:
        if self._current_app_id is None:
            return False
        return any(
            modifier == identity[0] and key.casefold() == identity[1].casefold()
            for modifier, key, _description in self._draft.list_shortcuts(
                self._current_app_id
            )
        )

    def _selected_builtin_identity(self) -> tuple[str, str] | None:
        row = self.builtin_table.currentRow()
        item = self.builtin_table.item(row, 0) if row >= 0 else None
        identity = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if (
            isinstance(identity, (list, tuple))
            and len(identity) == 2
            and all(isinstance(value, str) for value in identity)
        ):
            return identity[0], identity[1]
        return None

    def _selected_shortcut(self) -> tuple[str, str, str, str] | None:
        row = self.shortcut_table.currentRow()
        if row < 0:
            return None
        items = [self.shortcut_table.item(row, column) for column in range(4)]
        if any(item is None for item in items):
            return None
        return tuple(item.text() for item in items)  # type: ignore[return-value]

    def _update_candidate_label(self) -> None:
        candidate = self._candidate_tracker.current_candidate
        editable = self._candidate_tracker.editable_candidate()
        if editable is None:
            text = self.tr("Current app: not available")
        else:
            label = get_application_display_name(editable) or editable
            text = self.tr("Current app: {name} ({identity})").format(
                name=label,
                identity=editable,
            )
        self.candidate_label.setText(text)
        self.candidate_label.setToolTip(candidate or "")

    def _update_enabled_state(self) -> None:
        has_profile = self._current_app_id is not None
        enabled = not self._editing_blocked
        self.profile_list.setEnabled(enabled)
        self.add_current_button.setEnabled(enabled)
        self.delete_profile_button.setEnabled(enabled and has_profile)
        self.display_name_edit.setEnabled(enabled and has_profile)
        self.tabs.setEnabled(enabled and has_profile)
        self.shortcut_table.setEnabled(enabled and has_profile)
        self.builtin_table.setEnabled(enabled and has_profile)
        for button in (
            self.add_shortcut_button,
            self.edit_shortcut_button,
            self.delete_shortcut_button,
            self.move_up_button,
            self.move_down_button,
        ):
            button.setEnabled(enabled and has_profile)
        save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setEnabled(enabled)
        self._update_builtin_action_state()

    @Slot()
    def _update_builtin_action_state(self) -> None:
        enabled = not self._editing_blocked and self._current_app_id is not None
        identity = self._selected_builtin_identity()
        hidden = False
        if enabled and identity is not None and self._current_app_id is not None:
            hidden = self._draft.is_builtin_hidden(
                self._current_app_id,
                identity[0],
                identity[1],
            )
        self.hide_restore_builtin_button.setText(
            self.tr("Restore Built-in Shortcut")
            if hidden
            else self.tr("Hide Built-in Shortcut")
        )
        self.hide_restore_builtin_button.setEnabled(enabled and identity is not None)
        has_hidden = bool(
            self._draft.list_hidden_builtin_shortcuts(self._current_app_id)
            if enabled and self._current_app_id is not None
            else []
        )
        self.restore_all_builtins_button.setEnabled(enabled and has_hidden)

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, self.tr("Shortcut Manager"), message)

    def _show_profile_validation_error(
        self,
        error: ProfileValidationError,
    ) -> None:
        internal_message = str(error)
        if internal_message == "This modifier and key already exist in the user profile.":
            message = self.tr(
                "This key already exists for the selected modifier combination."
            )
        elif internal_message == "The shortcut being edited no longer exists.":
            message = self.tr("The shortcut being edited is no longer available.")
        elif internal_message == "Application ID must not be empty.":
            message = self.tr("Application ID must not be empty.")
        elif internal_message == "The current window is not a customizable application.":
            message = self.tr(
                "The current window is not a customizable application."
            )
        elif internal_message == "Select a supported modifier combination.":
            message = self.tr("Select a supported modifier combination.")
        elif internal_message == "Chinese description must not be empty.":
            message = self.tr("Chinese description must not be empty.")
        elif internal_message == "English description must not be empty.":
            message = self.tr("English description must not be empty.")
        else:
            message = self.tr(
                "The user profile data is invalid. Please review it and try again."
            )
        self._show_warning(message)

    def _show_save_error(self, _error: BaseException) -> None:
        QMessageBox.critical(
            self,
            self.tr("Shortcut Manager"),
            self.tr("Save failed. The original configuration was not changed."),
        )

    def _confirm(self, message: str) -> bool:
        return (
            QMessageBox.question(
                self,
                self.tr("Shortcut Manager"),
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )
