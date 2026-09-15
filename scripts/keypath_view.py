"""In-window KeyPath presentation; this is not a new top-level window."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .keypath_model import KeyPathLevel, KeyPathSession


class _KeyPathOptionRow(QFrame):
    activated = Signal(str)

    def __init__(self, identity: str, hint: str, label: str, detail: str, object_name: str, parent=None) -> None:
        super().__init__(parent)
        self.identity = identity
        self.setObjectName(object_name)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        line = QHBoxLayout(self)
        line.setContentsMargins(8, 7, 8, 7)
        line.setSpacing(10)
        hint_label = QLabel(f"[{hint}]", self)
        hint_label.setObjectName("keypathHint")
        hint_label.setFixedWidth(42 if len(hint) == 1 else 54)
        label_widget = QLabel(label, self)
        label_widget.setObjectName("keypathOptionLabel")
        label_widget.setTextFormat(Qt.TextFormat.PlainText)
        label_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        detail_widget = QLabel(detail, self)
        detail_widget.setObjectName("keypathOptionDetail")
        detail_widget.setTextFormat(Qt.TextFormat.PlainText)
        line.addWidget(hint_label)
        line.addWidget(label_widget, 1)
        line.addWidget(detail_widget)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.identity)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class KeyPathPanel(QScrollArea):
    category_selected = Signal(str)
    action_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("keypathPanel")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._session = None
        self.content = QWidget(self)
        self.content.setObjectName("keypathContent")
        self.content.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.root_layout = QVBoxLayout(self.content)
        self.root_layout.setContentsMargins(6, 8, 10, 8)
        self.root_layout.setSpacing(10)
        self.setWidget(self.content)
        self.setStyleSheet("""
            QScrollArea#keypathPanel, QWidget#keypathContent { background: #20232e; border: none; }
            QLabel { color: #dce2ed; background: transparent; }
            QLabel#keypathLevelTitle { color: #f1f5fb; font-size: 18px; font-weight: 600; }
            QLabel#keypathLevelSubtitle { color: #7f8ba0; font-size: 11px; }
            QFrame#keypathCategoryRow, QFrame#keypathActionRow {
                background: transparent; border: none; border-bottom: 1px solid #303746; border-radius: 3px;
            }
            QFrame#keypathCategoryRow:hover, QFrame#keypathActionRow:hover { background: #2a303d; }
            QLabel#keypathHint { color: #9fc4f4; font-size: 13px; font-weight: 700; }
            QLabel#keypathOptionLabel { color: #dce2ed; font-size: 13px; }
            QLabel#keypathOptionDetail { color: #8f9bb0; font-size: 11px; }
            QLabel#keypathResultCategory { color: #8fa4bf; font-size: 13px; }
            QLabel#keypathResultLabel { color: #f1f5fb; font-size: 21px; font-weight: 600; }
            QLabel#keypathResultTrigger { color: #b8d8ff; font-size: 34px; font-weight: 700; padding: 18px; }
            QLabel#keypathResultPath { color: #8390a6; font-size: 12px; }
            QLabel#keypathEmpty { color: #9aa6b8; font-size: 14px; }
            QScrollBar:vertical { background: #20232e; width: 8px; }
            QScrollBar::handle:vertical { background: #55617a; border-radius: 4px; min-height: 28px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

    @property
    def session(self) -> KeyPathSession | None:
        return self._session

    def render_session(self, session: KeyPathSession) -> None:
        self._session = session
        self._clear()
        if session.level == KeyPathLevel.ROOT:
            self._render_root(session)
        elif session.level == KeyPathLevel.CATEGORY:
            self._render_category(session)
        else:
            self._render_result(session)
        self.verticalScrollBar().setValue(0)

    def _render_root(self, session: KeyPathSession) -> None:
        self._add_heading(self.tr("Path navigation"), self.tr("Choose a category"))
        if not session.dataset.categories:
            empty = QLabel(self.tr("No shortcuts available to navigate"), self.content)
            empty.setObjectName("keypathEmpty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.root_layout.addStretch(1)
            self.root_layout.addWidget(empty)
            self.root_layout.addStretch(1)
            return
        rows = []
        for category in session.dataset.categories:
            row = _KeyPathOptionRow(category.key, category.hint, category.title, self.tr("%1 shortcuts").replace("%1", str(len(category.actions))), "keypathCategoryRow", self.content)
            row.activated.connect(self.category_selected)
            rows.append(row)
        self.root_layout.addWidget(self._grid(rows))
        self.root_layout.addStretch(1)

    def _render_category(self, session: KeyPathSession) -> None:
        category = session.category
        if category is None:
            self._render_root(session)
            return
        self._add_heading(category.title, self.tr("Choose a shortcut"))
        rows = []
        for action in category.actions:
            row = _KeyPathOptionRow(action.entry_id, action.hint, action.label, action.trigger, "keypathActionRow", self.content)
            row.setToolTip(f"{action.label}\n{action.trigger}")
            row.activated.connect(self.action_selected)
            rows.append(row)
        self.root_layout.addWidget(self._grid(rows))
        self.root_layout.addStretch(1)

    def _render_result(self, session: KeyPathSession) -> None:
        category, result = session.category, session.result
        if category is None or result is None:
            self._render_root(session)
            return
        self.root_layout.addStretch(2)
        category_label = QLabel(category.title, self.content)
        category_label.setObjectName("keypathResultCategory")
        category_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_label = QLabel(result.label, self.content)
        result_label.setObjectName("keypathResultLabel")
        result_label.setTextFormat(Qt.TextFormat.PlainText)
        result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_label.setWordWrap(True)
        trigger_label = QLabel(result.trigger, self.content)
        trigger_label.setObjectName("keypathResultTrigger")
        trigger_label.setTextFormat(Qt.TextFormat.PlainText)
        trigger_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path_label = QLabel(" → ".join(session.path_hints), self.content)
        path_label.setObjectName("keypathResultPath")
        path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.root_layout.addWidget(category_label)
        self.root_layout.addWidget(result_label)
        self.root_layout.addWidget(trigger_label)
        self.root_layout.addWidget(path_label)
        self.root_layout.addStretch(3)

    def _add_heading(self, title: str, subtitle: str) -> None:
        title_label = QLabel(title, self.content)
        title_label.setObjectName("keypathLevelTitle")
        subtitle_label = QLabel(subtitle, self.content)
        subtitle_label.setObjectName("keypathLevelSubtitle")
        self.root_layout.addWidget(title_label)
        self.root_layout.addWidget(subtitle_label)

    def _grid(self, rows: list[_KeyPathOptionRow]) -> QWidget:
        grid_widget = QWidget(self.content)
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(3)
        width = max(1, self.viewport().width())
        columns = max(1, min(3, width // 400))
        for index, row in enumerate(rows):
            grid.addWidget(row, index // columns, index % columns)
        for column in range(columns):
            grid.setColumnStretch(column, 1)
        return grid_widget

    def _clear(self) -> None:
        while self.root_layout.count():
            item = self.root_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
