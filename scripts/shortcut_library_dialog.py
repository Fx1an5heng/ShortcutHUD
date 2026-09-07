"""Shortcut Center: Catalog browsing and existing USER shortcut editing in one view."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt, Slot
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView

from .application_descriptor import ApplicationDescriptor, ApplicationDescriptorFactory
from .catalog_application_registry import CatalogApplication, CatalogApplicationRegistry
from .quick_hud_selection_store import QuickHudSelectionStore
from .shortcut_catalog import CatalogEntry, CatalogTrigger, ShortcutCatalog, select_catalog_text
from .shortcut_resolver import normalize_application_identity
from .user_shortcut_manager_dialog import ProfileValidationError, ShortcutEditDialog, UserProfileDraft
from .user_shortcut_store import UserShortcutStore


@dataclass(frozen=True, slots=True)
class LibraryRow:
    entry: CatalogEntry
    source: str
    checked: bool
    title: str
    description: str


class ShortcutLibraryModel:
    """UI-independent Shortcut Center state; detected and supported apps differ."""

    def __init__(self, catalog: ShortcutCatalog, selection_store: QuickHudSelectionStore, user_profiles: Mapping[str, object] | None = None, language: str | None = None, current_application: str | None = None, recent_applications: tuple[str, ...] = (), *, current_descriptor: ApplicationDescriptor | None = None, recent_descriptors: tuple[ApplicationDescriptor, ...] = (), user_store: UserShortcutStore | None = None, apply_user_profiles: Callable[[Mapping[str, object]], None] | None = None) -> None:
        self.catalog, self.selection_store = catalog, selection_store
        self.user_profiles = dict(user_profiles) if isinstance(user_profiles, Mapping) else {}
        self.language = language
        self.registry = CatalogApplicationRegistry(catalog, self.user_profiles, language)
        self._descriptor_factory = ApplicationDescriptorFactory()
        self.user_store, self.apply_user_profiles = user_store, apply_user_profiles
        self.current_descriptor: ApplicationDescriptor | None = None
        self.recent_descriptors: tuple[ApplicationDescriptor, ...] = ()
        current = current_descriptor or self._descriptor_factory.describe(current_application)
        recent = recent_descriptors or tuple(item for value in recent_applications if (item := self._descriptor_factory.describe(value)) is not None)
        self.update_detected(current, recent)

    def update_detected(self, current: ApplicationDescriptor | None, recent: tuple[ApplicationDescriptor, ...] = ()) -> None:
        self.current_descriptor = self.registry.describe(current)
        seen: set[str] = set(); items: list[ApplicationDescriptor] = []
        for descriptor in recent:
            decorated = self.registry.describe(descriptor)
            if decorated is not None and decorated.runtime_identity not in seen:
                seen.add(decorated.runtime_identity); items.append(decorated)
        self.recent_descriptors = tuple(items[:8])

    def applications(self) -> list[tuple[str, str]]:
        return [(item.primary_identity, item.display_name) for item in self.registry.supported_applications()]

    def current_record(self) -> CatalogApplication | None:
        return self.registry.find_by_identity(self.current_descriptor.runtime_identity if self.current_descriptor else None)

    def recent_records(self) -> list[CatalogApplication]:
        return [item for descriptor in self.recent_descriptors if (item := self.registry.find_by_identity(descriptor.runtime_identity)) is not None]

    def descriptor_for(self, app_id: str | None) -> ApplicationDescriptor | None:
        identity = normalize_application_identity(app_id)
        if identity is None: return None
        for descriptor in (self.current_descriptor, *self.recent_descriptors):
            if descriptor is not None and descriptor.runtime_identity == identity: return descriptor
        record = self.registry.find_by_identity(identity)
        return self.registry.describe(self._descriptor_factory.describe(record.primary_identity if record else identity))

    def supported_descriptors(self) -> list[ApplicationDescriptor]:
        return [descriptor for record in self.registry.supported_applications() if (descriptor := self.registry.describe(self._descriptor_factory.describe(record.primary_identity))) is not None]

    def rows(self, app_id: str, query: str = "") -> list[LibraryRow]:
        identity = normalize_application_identity(app_id)
        if identity is None: return []
        entries = self._entries_for_application(identity)
        explicit = self.selection_store.effective_selected_ids_for(identity, [entry for entry, _ in entries])
        folded_query = query.casefold().strip(); rows: list[LibraryRow] = []
        for entry, source in entries:
            title = select_catalog_text(entry.title, self.language); description = _localized_description(entry.description, self.language); category = self.category_label(entry.category)
            category_values = self.catalog.category_titles.get(entry.category, {}).values()
            terms = (_trigger_text(entry), entry.hud_key(), title, description, category, entry.category, *category_values, *entry.title.values(), *_description_values(entry.description), *entry.aliases)
            if folded_query and not any(folded_query in term.casefold() for term in terms): continue
            rows.append(LibraryRow(entry, source, entry.recommended if explicit is None else entry.id in explicit, title, description))
        return rows

    def category_label(self, category: str) -> str:
        is_chinese = isinstance(self.language, str) and self.language.casefold().startswith("zh")
        if category == "legacy": return "其他" if is_chinese else "Other"
        if category == "user": return "我的快捷键" if is_chinese else "My Shortcuts"
        labels = self.catalog.category_titles.get(category)
        return select_catalog_text(labels, self.language) if labels else category

    def set_checked(self, app_id: str, entry_id: str, checked: bool) -> None:
        identity = _require_identity(app_id); entries = [entry for entry, _ in self._entries_for_application(identity)]
        selected = self.selection_store.effective_selected_ids_for(identity, entries)
        chosen = set(selected) if selected is not None else {entry.id for entry in entries if entry.recommended}
        chosen.add(entry_id) if checked else chosen.discard(entry_id)
        self.selection_store.set_selected_ids(identity, chosen); self.selection_store.save()

    def clear_all(self, app_id: str) -> None:
        self.selection_store.set_selected_ids(app_id, []); self.selection_store.save()

    def restore_recommended(self, app_id: str) -> None:
        self.selection_store.clear_selection(app_id); self.selection_store.save()

    def add_user_shortcut(self, app_id: str, modifier: str, key: str, zh: str, en: str) -> None:
        self._mutate_user(app_id, lambda draft, identity: draft.add_shortcut(identity, modifier, key, zh, en))

    def edit_user_shortcut(self, app_id: str, old_modifier: str, old_key: str, modifier: str, key: str, zh: str, en: str) -> None:
        self._mutate_user(app_id, lambda draft, identity: draft.edit_shortcut(identity, old_modifier, old_key, modifier, key, zh, en))

    def delete_user_shortcut(self, app_id: str, modifier: str, key: str) -> bool:
        changed = False
        def mutate(draft: UserProfileDraft, identity: str) -> None:
            nonlocal changed
            changed = draft.delete_shortcut(identity, modifier, key)
        self._mutate_user(app_id, mutate, create_profile=False)
        return changed

    def user_shortcut_description(self, app_id: str, modifier: str, key: str) -> tuple[str, str]:
        profile = next((value for name, value in self.user_profiles.items() if normalize_application_identity(name) == normalize_application_identity(app_id) and isinstance(value, Mapping)), {})
        shortcuts = profile.get("shortcuts", {}) if isinstance(profile, Mapping) else {}
        group = shortcuts.get(modifier, {}) if isinstance(shortcuts, Mapping) else {}
        value = group.get(key, {}) if isinstance(group, Mapping) else {}
        return (
            str(value.get("zh", "")) if isinstance(value, Mapping) else "",
            str(value.get("en", "")) if isinstance(value, Mapping) else "",
        )

    def _mutate_user(self, app_id: str, mutation: Callable[[UserProfileDraft, str], None], *, create_profile: bool = True) -> None:
        identity = _require_identity(app_id); draft = UserProfileDraft(self.user_profiles)
        if draft.get_profile(identity) is None:
            if not create_profile: return
            draft.add_profile(identity)
        mutation(draft, identity); draft.validate_all(); snapshot = draft.snapshot()
        if self.user_store is not None:
            transaction = UserShortcutStore(self.user_store.path); transaction.replace_snapshot(snapshot); transaction.save(); snapshot = transaction.snapshot(); self.user_store.replace_snapshot(snapshot)
        self.user_profiles = snapshot; self.registry = CatalogApplicationRegistry(self.catalog, self.user_profiles, self.language)
        self.update_detected(self.current_descriptor, self.recent_descriptors)
        if self.apply_user_profiles is not None: self.apply_user_profiles(snapshot)

    def _entries_for_application(self, app_id: str) -> list[tuple[CatalogEntry, str]]:
        builtin = [(entry, "builtin") for entry in self.catalog.entries if entry.scope == "APP" and app_id in entry.application_ids and "quick_hud" in entry.visibility]
        return sorted([*_user_catalog_entries(self.user_profiles, app_id), *builtin], key=lambda item: (item[0].category.casefold(), item[0].rank, item[0].order, item[0].id))


class ShortcutLibraryDialog(QDialog):
    """The user-facing Shortcut Center; historic class name stays compatible."""

    def __init__(self, model: ShortcutLibraryModel, parent=None, candidate_tracker: object | None = None, advanced_manager_opener: Callable[[], None] | None = None) -> None:
        super().__init__(parent); self.model, self._candidate_tracker, self._advanced_manager_opener, self._rendering, self._populating = model, candidate_tracker, advanced_manager_opener, False, False
        self.setObjectName("ShortcutCenterDialog"); self.setWindowTitle(self.tr("Shortcut Center")); self.resize(920, 580)
        layout = QVBoxLayout(self); header = QHBoxLayout(); self.follow_current_checkbox = QCheckBox(self.tr("Follow Current App"), self); self.application_combo = QComboBox(self); self.search_box = QLineEdit(self); self.search_box.setPlaceholderText(self.tr("Search shortcuts"))
        header.addWidget(self.follow_current_checkbox); header.addWidget(QLabel(self.tr("Application:"), self)); header.addWidget(self.application_combo, 1); header.addWidget(self.search_box, 2); layout.addLayout(header)
        self.empty_builtin_label = QLabel(self.tr("No built-in shortcut data for this application."), self); self.empty_builtin_label.setVisible(False); layout.addWidget(self.empty_builtin_label)
        self.selection_label = QLabel(self); layout.addWidget(self.selection_label); self.table = QTableWidget(0, 6, self); self.table.setHorizontalHeaderLabels([self.tr("Show"), self.tr("Shortcut"), self.tr("Description"), self.tr("Category"), self.tr("Source"), self.tr("Recommended")]); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.verticalHeader().setVisible(False)
        for index in (0, 1, 4, 5): self.table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch); self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents); layout.addWidget(self.table, 1)
        actions = QHBoxLayout(); self.add_button = QPushButton(self.tr("Add Shortcut"), self); self.edit_button = QPushButton(self.tr("Edit"), self); self.delete_button = QPushButton(self.tr("Delete"), self); self.restore_button = QPushButton(self.tr("Restore Recommended"), self); self.clear_button = QPushButton(self.tr("Clear All"), self); self.advanced_button = QPushButton(self.tr("Advanced Management..."), self)
        for button in (self.add_button, self.edit_button, self.delete_button, self.restore_button, self.clear_button, self.advanced_button): actions.addWidget(button)
        actions.addStretch(1); layout.addLayout(actions); buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.setStyleSheet("QDialog#ShortcutCenterDialog { background: #2E2E3A; color: #D8DEE9; } QLabel { color: #D8DEE9; } QLineEdit, QComboBox, QTableWidget { color: #D8DEE9; background: #4A4E5A; border: 1px solid #5A5E6A; } QPushButton { color: #D8DEE9; background: #4A4E5A; border: 1px solid #5A5E6A; padding: 5px 10px; }")
        self.follow_current_checkbox.setChecked(True); self._populate_applications(select_identity=self._current_identity())
        self.application_combo.currentIndexChanged.connect(self._on_application_changed); self.search_box.textChanged.connect(self._render); self.table.itemChanged.connect(self._on_item_changed); self.table.itemSelectionChanged.connect(self._update_action_state); self.follow_current_checkbox.toggled.connect(self._on_follow_changed)
        self.add_button.clicked.connect(self._add_shortcut); self.edit_button.clicked.connect(self._edit_shortcut); self.delete_button.clicked.connect(self._delete_shortcut); self.restore_button.clicked.connect(self._restore_recommended); self.clear_button.clicked.connect(self._clear_all); self.advanced_button.clicked.connect(self._open_advanced_manager); self.advanced_button.setVisible(advanced_manager_opener is not None)
        signal = getattr(candidate_tracker, "foreground_context_changed", None) or getattr(candidate_tracker, "candidate_changed", None)
        if signal is not None and hasattr(signal, "connect"): signal.connect(self._on_candidate_changed)
        self._render()

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.WindowActivate: self._follow_latest_candidate()
        return super().event(event)

    def _current_identity(self) -> str | None:
        return self.model.current_descriptor.runtime_identity if self.model.current_descriptor else None

    def _populate_applications(self, *, select_identity: str | None) -> None:
        self._populating = True; self.application_combo.clear(); current = self.model.current_descriptor
        if current is not None: self._add_group_header(self.tr("Current Application")); self.application_combo.addItem(self._display_name(current), current.runtime_identity)
        if self.model.recent_descriptors:
            self._add_group_header(self.tr("Recent Applications"))
            for descriptor in self.model.recent_descriptors:
                if current is None or descriptor.runtime_identity != current.runtime_identity: self.application_combo.addItem(self._display_name(descriptor), descriptor.runtime_identity)
        self._add_group_header(self.tr("All Supported Applications")); seen: set[str] = set()
        for descriptor in self.model.supported_descriptors():
            if descriptor.runtime_identity not in seen: seen.add(descriptor.runtime_identity); self.application_combo.addItem(self._display_name(descriptor), descriptor.runtime_identity)
        target = self.application_combo.findData(select_identity) if select_identity else -1; self.application_combo.setCurrentIndex(target if target >= 0 else (1 if self.application_combo.count() > 1 else -1)); self._populating = False

    def _add_group_header(self, label: str) -> None:
        index = self.application_combo.count(); self.application_combo.addItem(label); item = self.application_combo.model().item(index)
        if item is not None: item.setEnabled(False)

    def _display_name(self, descriptor: ApplicationDescriptor) -> str:
        return self.tr("Windows Desktop") if descriptor.context_kind == "desktop" else descriptor.display_name

    def _current_app_id(self) -> str | None:
        value = self.application_combo.currentData(); return value if isinstance(value, str) else None

    @Slot()
    def _render(self) -> None:
        app_id = self._current_app_id(); descriptor = self.model.descriptor_for(app_id); rows = self.model.rows(app_id or "", self.search_box.text()); self._rendering = True; self.table.setRowCount(len(rows)); self.empty_builtin_label.setVisible(descriptor is not None and not descriptor.supported); self.selection_label.setText(self.tr("Selected for Quick HUD: %1").replace("%1", str(sum(row.checked for row in self.model.rows(app_id or "")))))
        for index, row in enumerate(rows):
            checkbox = QTableWidgetItem(); checkbox.setData(Qt.ItemDataRole.UserRole, row.entry.id); checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable); checkbox.setCheckState(Qt.CheckState.Checked if row.checked else Qt.CheckState.Unchecked); self.table.setItem(index, 0, checkbox); self.table.setItem(index, 1, QTableWidgetItem(_trigger_text(row.entry))); self.table.setItem(index, 2, QTableWidgetItem(row.description)); self.table.setItem(index, 3, QTableWidgetItem(self.model.category_label(row.entry.category)))
            source_item = QTableWidgetItem(self.tr("My Shortcut") if row.source == "user" else self.tr("Built-in")); source_item.setData(Qt.ItemDataRole.UserRole, row.source); source_item.setData(Qt.ItemDataRole.UserRole + 1, (row.entry.legacy_runtime_modifier, row.entry.legacy_display_key)); self.table.setItem(index, 4, source_item); self.table.setItem(index, 5, QTableWidgetItem(self.tr("★ Recommended") if row.entry.recommended else ""))
        self._rendering = False; self._update_action_state()

    @Slot(int)
    def _on_application_changed(self, _index: int) -> None:
        if not self._populating: self.follow_current_checkbox.setChecked(False)
        self._render()

    @Slot(bool)
    def _on_follow_changed(self, enabled: bool) -> None:
        if enabled: self._follow_latest_candidate()

    @Slot(object)
    def _on_candidate_changed(self, _candidate: object) -> None: self._follow_latest_candidate()

    def _follow_latest_candidate(self) -> None:
        if not self.follow_current_checkbox.isChecked() or self._candidate_tracker is None: return
        current = getattr(self._candidate_tracker, "center_context", None) or getattr(self._candidate_tracker, "current_descriptor", None); recent = getattr(self._candidate_tracker, "recent_descriptors", ())
        if current is None: return
        self.model.update_detected(current, tuple(recent) if isinstance(recent, tuple) else ()); self._populate_applications(select_identity=current.runtime_identity); self._render()

    @Slot(QTableWidgetItem)
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._rendering or item.column() != 0: return
        app_id = self._current_app_id(); entry_id = item.data(Qt.ItemDataRole.UserRole)
        if app_id is not None and isinstance(entry_id, str): self.model.set_checked(app_id, entry_id, item.checkState() == Qt.CheckState.Checked); self._render()

    def _selected_user_identity(self) -> tuple[str, str] | None:
        row = self.table.currentRow(); source = self.table.item(row, 4) if row >= 0 else None; data = source.data(Qt.ItemDataRole.UserRole + 1) if source is not None else None
        return (data[0], data[1]) if source is not None and source.data(Qt.ItemDataRole.UserRole) == "user" and isinstance(data, tuple) and len(data) == 2 and all(isinstance(item, str) for item in data) else None

    @Slot()
    def _add_shortcut(self) -> None:
        app_id = self._current_app_id()
        if app_id is None: return
        editor = ShortcutEditDialog(self)
        if editor.exec() == QDialog.DialogCode.Accepted:
            try: self.model.add_user_shortcut(app_id, *editor.values())
            except ProfileValidationError as error: QMessageBox.warning(self, self.windowTitle(), str(error)); return
            self._render()

    @Slot()
    def _edit_shortcut(self) -> None:
        app_id = self._current_app_id(); selected = self._selected_user_identity()
        if app_id is None or selected is None: return
        zh, en = self.model.user_shortcut_description(app_id, *selected); editor = ShortcutEditDialog(self, modifier=selected[0], key=selected[1], zh=zh, en=en)
        if editor.exec() == QDialog.DialogCode.Accepted:
            try: self.model.edit_user_shortcut(app_id, *selected, *editor.values())
            except ProfileValidationError as error: QMessageBox.warning(self, self.windowTitle(), str(error)); return
            self._render()

    @Slot()
    def _delete_shortcut(self) -> None:
        app_id = self._current_app_id(); selected = self._selected_user_identity()
        if app_id is not None and selected is not None and self.model.delete_user_shortcut(app_id, *selected): self._render()

    @Slot()
    def _open_advanced_manager(self) -> None:
        if self._advanced_manager_opener is not None: self._advanced_manager_opener()

    @Slot()
    def _restore_recommended(self) -> None:
        if (app_id := self._current_app_id()) is not None: self.model.restore_recommended(app_id); self._render()

    @Slot()
    def _clear_all(self) -> None:
        if (app_id := self._current_app_id()) is not None: self.model.clear_all(app_id); self._render()

    def _update_action_state(self) -> None:
        descriptor = self.model.descriptor_for(self._current_app_id())
        editable = descriptor is not None and descriptor.context_kind == "application"; self.add_button.setEnabled(editable); selected = self._selected_user_identity() is not None; self.edit_button.setEnabled(selected); self.delete_button.setEnabled(selected)


ShortcutCenterDialog = ShortcutLibraryDialog


def _require_identity(app_id: str) -> str:
    identity = normalize_application_identity(app_id)
    if identity is None: raise ValueError("invalid application identity")
    return identity


def _localized_description(value: object, language: str | None) -> str:
    if isinstance(value, Mapping): return select_catalog_text({key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, str)}, language)
    return value if isinstance(value, str) else ""


def _description_values(value: object) -> tuple[str, ...]:
    return tuple(item for item in value.values() if isinstance(item, str)) if isinstance(value, Mapping) else (value,) if isinstance(value, str) else ()


def _trigger_text(entry: CatalogEntry) -> str:
    return "+".join(entry.trigger.keys) if entry.trigger.kind == "combo" else " ".join(entry.trigger.keys)


def _user_catalog_entries(profiles: Mapping[str, object], app_id: str) -> list[tuple[CatalogEntry, str]]:
    profile = next((value for key, value in profiles.items() if normalize_application_identity(key) == app_id and isinstance(value, Mapping)), None)
    if not isinstance(profile, Mapping) or not isinstance(profile.get("shortcuts"), Mapping): return []
    entries: list[tuple[CatalogEntry, str]] = []; order = -100000
    for modifier, keys in profile["shortcuts"].items():
        if not isinstance(modifier, str) or not isinstance(keys, Mapping): continue
        for key, description in keys.items():
            if not isinstance(key, str): continue
            entry = CatalogEntry(id=f"user:{app_id.casefold()}:{modifier.casefold()}:{key.casefold()}", trigger=CatalogTrigger("combo", tuple(modifier.split("+")) + (key,)), title={"en": key}, description=description, category="user", scope="APP", application_ids=(app_id,), recommended=True, rank=order, provenance={"kind": "user"}, visibility=frozenset({"quick_hud"}), builtin=False, aliases=(), order=order, legacy_runtime_modifier=modifier, legacy_display_key=key)
            entries.append((entry, "user")); order += 1
    return entries
