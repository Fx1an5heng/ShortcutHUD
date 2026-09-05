"""Shortcut Library: choose which resolved Catalog entries enter Quick HUD."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

from .application_display_names import get_application_display_name
from .quick_hud_selection_store import QuickHudSelectionStore
from .shortcut_catalog import CatalogEntry, CatalogTrigger, ShortcutCatalog, select_catalog_text
from .shortcut_resolver import RESERVED_USER_IDENTITIES, normalize_application_identity


@dataclass(frozen=True, slots=True)
class LibraryRow:
    entry: CatalogEntry
    source: str
    checked: bool
    title: str
    description: str


class ShortcutLibraryModel:
    """In-memory catalog view and selection mutations, isolated from Qt widgets."""

    def __init__(
        self,
        catalog: ShortcutCatalog,
        selection_store: QuickHudSelectionStore,
        user_profiles: Mapping[str, object] | None = None,
        language: str | None = None,
    ) -> None:
        self.catalog = catalog
        self.selection_store = selection_store
        self.user_profiles = dict(user_profiles) if isinstance(user_profiles, Mapping) else {}
        self.language = language

    def applications(self) -> list[tuple[str, str]]:
        identities = {
            app_id
            for entry in self.catalog.entries
            if entry.scope == "APP"
            for app_id in entry.application_ids
        }
        identities.update(
            identity for raw_id in self.user_profiles
            if (identity := normalize_application_identity(raw_id)) is not None
            and identity not in RESERVED_USER_IDENTITIES
        )
        return sorted(
            ((identity, self._app_label(identity)) for identity in identities),
            key=lambda item: (item[1].casefold(), item[0]),
        )

    def rows(self, app_id: str, query: str = "") -> list[LibraryRow]:
        identity = normalize_application_identity(app_id)
        if identity is None:
            return []
        entries = self._entries_for_application(identity)
        explicit = self.selection_store.effective_selected_ids_for(
            identity, [entry for entry, _source in entries]
        )
        folded_query = query.casefold().strip()
        rows: list[LibraryRow] = []
        for entry, source in entries:
            title = select_catalog_text(entry.title, self.language)
            description = _localized_description(entry.description, self.language)
            search_terms = (
                _trigger_text(entry), entry.hud_key(), title, description, entry.category,
                *entry.title.values(), *_description_values(entry.description), *entry.aliases,
            )
            if folded_query and not any(folded_query in term.casefold() for term in search_terms):
                continue
            checked = entry.recommended if explicit is None else entry.id in explicit
            rows.append(LibraryRow(entry, source, checked, title, description))
        return rows

    def set_checked(self, app_id: str, entry_id: str, checked: bool) -> None:
        identity = normalize_application_identity(app_id)
        if identity is None:
            raise ValueError("invalid application identity")
        entries = [entry for entry, _source in self._entries_for_application(identity)]
        selected = self.selection_store.effective_selected_ids_for(identity, entries)
        chosen = set(selected) if selected is not None else {
            entry.id for entry in entries if entry.recommended
        }
        if checked:
            chosen.add(entry_id)
        else:
            chosen.discard(entry_id)
        self.selection_store.set_selected_ids(identity, chosen)
        self.selection_store.save()

    def clear_all(self, app_id: str) -> None:
        self.selection_store.set_selected_ids(app_id, [])
        self.selection_store.save()

    def restore_recommended(self, app_id: str) -> None:
        self.selection_store.clear_selection(app_id)
        self.selection_store.save()

    def _entries_for_application(self, app_id: str) -> list[tuple[CatalogEntry, str]]:
        builtin = [
            entry for entry in self.catalog.entries
            if entry.scope == "APP" and app_id in entry.application_ids and "quick_hud" in entry.visibility
        ]
        user = _user_catalog_entries(self.user_profiles, app_id)
        return sorted(
            [*user, *[(entry, "APP") for entry in builtin]],
            key=lambda item: (item[0].category.casefold(), item[0].rank, item[0].order, item[0].id),
        )

    def _app_label(self, app_id: str) -> str:
        title = self.catalog.application_titles.get(app_id)
        if title:
            return select_catalog_text(title, self.language)
        return get_application_display_name(app_id) or app_id


class ShortcutLibraryDialog(QDialog):
    """Compact table-oriented Library UI; changes save immediately and atomically."""

    def __init__(self, model: ShortcutLibraryModel, parent=None) -> None:
        super().__init__(parent)
        self.model = model
        self._rendering = False
        self.setObjectName("ShortcutLibraryDialog")
        self.setWindowTitle(self.tr("Shortcut Library"))
        self.resize(800, 560)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.application_combo = QComboBox(self)
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText(self.tr("Search shortcuts"))
        header.addWidget(QLabel(self.tr("Application:"), self))
        header.addWidget(self.application_combo, 1)
        header.addWidget(self.search_box, 2)
        layout.addLayout(header)
        self.selection_label = QLabel(self)
        layout.addWidget(self.selection_label)
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels([self.tr("Show"), self.tr("Shortcut"), self.tr("Description"), self.tr("Category")])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.restore_button = QPushButton(self.tr("Restore Recommended"), self)
        self.clear_button = QPushButton(self.tr("Clear All"), self)
        actions.addWidget(self.restore_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet("QDialog#ShortcutLibraryDialog { background: #2E2E3A; color: #D8DEE9; } QLabel { color: #D8DEE9; } QLineEdit, QComboBox, QTableWidget { color: #D8DEE9; background: #4A4E5A; border: 1px solid #5A5E6A; } QPushButton { color: #D8DEE9; background: #4A4E5A; border: 1px solid #5A5E6A; padding: 5px 10px; }")
        for app_id, label in self.model.applications():
            self.application_combo.addItem(label, app_id)
        self.application_combo.currentIndexChanged.connect(self._render)
        self.search_box.textChanged.connect(self._render)
        self.table.itemChanged.connect(self._on_item_changed)
        self.restore_button.clicked.connect(self._restore_recommended)
        self.clear_button.clicked.connect(self._clear_all)
        self._render()

    def _current_app_id(self) -> str | None:
        value = self.application_combo.currentData()
        return value if isinstance(value, str) else None

    @Slot()
    def _render(self) -> None:
        app_id = self._current_app_id()
        rows = self.model.rows(app_id or "", self.search_box.text())
        self._rendering = True
        self.table.setRowCount(len(rows))
        selected_count = sum(row.checked for row in self.model.rows(app_id or ""))
        self.selection_label.setText(self.tr("Selected for Quick HUD: %1").replace("%1", str(selected_count)))
        for index, row in enumerate(rows):
            checkbox = QTableWidgetItem()
            checkbox.setData(Qt.ItemDataRole.UserRole, row.entry.id)
            checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            checkbox.setCheckState(Qt.CheckState.Checked if row.checked else Qt.CheckState.Unchecked)
            self.table.setItem(index, 0, checkbox)
            self.table.setItem(index, 1, QTableWidgetItem(_trigger_text(row.entry)))
            description = row.description
            if row.entry.recommended:
                description = f"{description} · {self.tr('Recommended')}"
            self.table.setItem(index, 2, QTableWidgetItem(description))
            self.table.setItem(index, 3, QTableWidgetItem(row.entry.category))
        self._rendering = False

    @Slot(QTableWidgetItem)
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._rendering or item.column() != 0:
            return
        app_id = self._current_app_id()
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if app_id is None or not isinstance(entry_id, str):
            return
        self.model.set_checked(app_id, entry_id, item.checkState() == Qt.CheckState.Checked)
        self._render()

    @Slot()
    def _restore_recommended(self) -> None:
        app_id = self._current_app_id()
        if app_id is not None:
            self.model.restore_recommended(app_id)
            self._render()

    @Slot()
    def _clear_all(self) -> None:
        app_id = self._current_app_id()
        if app_id is not None:
            self.model.clear_all(app_id)
            self._render()


def _localized_description(value: object, language: str | None) -> str:
    if isinstance(value, Mapping):
        text = {key: item for key, item in value.items() if isinstance(key, str) and isinstance(item, str)}
        return select_catalog_text(text, language)
    return value if isinstance(value, str) else ""


def _description_values(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return tuple(item for item in value.values() if isinstance(item, str))
    return (value,) if isinstance(value, str) else ()


def _trigger_text(entry: CatalogEntry) -> str:
    if entry.trigger.kind == "combo":
        return "+".join(entry.trigger.keys)
    return " ".join(entry.trigger.keys)


def _user_catalog_entries(profiles: Mapping[str, object], app_id: str) -> list[tuple[CatalogEntry, str]]:
    profile = next((value for key, value in profiles.items() if normalize_application_identity(key) == app_id and isinstance(value, Mapping)), None)
    if not isinstance(profile, Mapping) or not isinstance(profile.get("shortcuts"), Mapping):
        return []
    entries: list[tuple[CatalogEntry, str]] = []
    order = -100000
    for modifier, keys in profile["shortcuts"].items():
        if not isinstance(modifier, str) or not isinstance(keys, Mapping):
            continue
        for key, description in keys.items():
            if not isinstance(key, str):
                continue
            entries.append((CatalogEntry(
                id=f"user:{app_id.casefold()}:{modifier.casefold()}:{key.casefold()}", trigger=CatalogTrigger("combo", tuple(modifier.split("+")) + (key,)), title={"en": key}, description=description, category="user", scope="APP", application_ids=(app_id,), recommended=True, rank=order, provenance={"kind": "user"}, visibility=frozenset({"quick_hud"}), builtin=False, aliases=(), order=order, legacy_runtime_modifier=modifier, legacy_display_key=key,
            ), "USER_APP"))
            order += 1
    return entries
