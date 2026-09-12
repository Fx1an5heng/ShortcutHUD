"""Large, focus-owning, read-only shortcut reference built with Qt Widgets."""
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .full_guide_context import guide_geometry
from .full_guide_model import balance_categories, column_count_for_width, group_entries


class FullGuideWindow(QWidget):
    closed = Signal()
    center_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("FullGuideWindow")
        self.setWindowTitle(self.tr("Full Guide"))
        self._session_open = False
        self.snapshot = None
        self.rows = ()
        self.sections = ()
        self.rendered_columns = ()
        self._debug_column_count = None
        self._last_width = 0
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(35)
        self._layout_timer.timeout.connect(self._render_sections)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 16)
        layout.setSpacing(16)
        top = QHBoxLayout()
        top.setSpacing(16)
        identity = QVBoxLayout()
        self.app_label = QLabel(self)
        self.app_label.setObjectName("guideApplication")
        self.app_label.setTextFormat(Qt.TextFormat.PlainText)
        self.count_label = QLabel(self)
        self.count_label.setObjectName("guideCount")
        identity.addWidget(self.app_label)
        identity.addWidget(self.count_label)
        top.addLayout(identity, 2)
        self.search_box = QLineEdit(self)
        self.search_box.setObjectName("guideSearch")
        self.search_box.setPlaceholderText(self.tr("Search shortcuts…"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(170)
        top.addWidget(self.search_box, 2)
        self.close_button = QPushButton("×", self)
        self.close_button.setObjectName("guideClose")
        self.close_button.setAccessibleName(self.tr("Close"))
        self.close_button.setToolTip(self.tr("Close"))
        self.close_button.clicked.connect(self.close)
        top.addWidget(self.close_button)
        layout.addLayout(top)
        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("guideContent")
        self.columns_layout = QHBoxLayout(self.content)
        self.columns_layout.setContentsMargins(0, 0, 4, 0)
        self.columns_layout.setSpacing(18)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.empty_panel = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_panel)
        self.empty_label = QLabel(self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.center_button = QPushButton(self.tr("Open Shortcut Center"), self)
        self.center_button.clicked.connect(self._open_center)
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_label)
        empty_layout.addWidget(self.center_button, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        layout.addWidget(self.empty_panel, 1)
        self.footer = QLabel(self.tr("Ctrl+F  Search     Esc  Clear search / Close     ★  Recommended"), self)
        self.footer.setObjectName("guideFooter")
        layout.addWidget(self.footer)
        self.search_box.textChanged.connect(self._search_changed)
        self._find = QShortcut(QKeySequence("Ctrl+F"), self)
        self._find.activated.connect(self._focus_search)
        self._escape = QShortcut(QKeySequence("Esc"), self)
        self._escape.activated.connect(self.escape)
        self.setStyleSheet("""
            QWidget#FullGuideWindow { background: #20232e; border: 1px solid #495264; }
            QWidget#guideContent { background: #20232e; }
            QLabel { color: #dce2ed; background: transparent; font-size: 13px; }
            QLabel#guideApplication { color: #f4f7fc; font-size: 26px; font-weight: 600; }
            QLabel#guideCount, QLabel#guideFooter { color: #939fb4; font-size: 12px; }
            QLineEdit#guideSearch { color: #edf2fa; background: #2b3040; border: 1px solid #4b5670;
                border-radius: 8px; padding: 11px 14px; font-size: 14px; }
            QLineEdit#guideSearch:focus { border-color: #91b6ec; }
            QPushButton { color: #dce2ed; background: #303747; border: 1px solid #485269;
                border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover { background: #46536b; }
            QPushButton#guideClose { font-size: 24px; padding: 2px 12px; border: none; background: transparent; }
            QFrame#guideSection { background: #272c39; border: 1px solid #353e50; border-radius: 8px; }
            QLabel#guideCategory { color: #9fc4f4; font-size: 15px; font-weight: 600; padding-bottom: 7px; }
            QFrame#guideRow { background: transparent; border: none; }
            QFrame#guideRow:hover { background: #343d4e; border-radius: 4px; }
            QLabel#guideTrigger { color: #b8cff3; font-size: 12px; font-weight: 600; }
            QLabel#guideBadge { color: #a99468; font-size: 11px; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: #20232e; width: 8px; }
            QScrollBar::handle:vertical { background: #55617a; border-radius: 4px; min-height: 28px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

    def present(self, snapshot, rows, language=None) -> None:
        self.snapshot, self.rows = snapshot, tuple(rows)
        self.app_label.setText(snapshot.descriptor.display_name)
        self.search_box.blockSignals(True)
        self.search_box.clear()
        self.search_box.blockSignals(False)
        self.setGeometry(guide_geometry(snapshot.available_geometry))
        self._session_open = True
        self._render_sections()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.scroll.verticalScrollBar().setValue(0)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.setWindowTitle(self.tr("Full Guide"))
            self.search_box.setPlaceholderText(self.tr("Search shortcuts…"))
            self.close_button.setAccessibleName(self.tr("Close"))
            self.close_button.setToolTip(self.tr("Close"))
            self.center_button.setText(self.tr("Open Shortcut Center"))
            self.footer.setText(self.tr("Ctrl+F  Search     Esc  Clear search / Close     ★  Recommended"))
            self._render_sections()
        super().changeEvent(event)

    def _focus_search(self) -> None:
        self.search_box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_box.selectAll()

    def escape(self) -> None:
        if self.search_box.text():
            self.search_box.clear()
        else:
            self.close()

    def _open_center(self) -> None:
        self.close()
        self.center_requested.emit()

    def _search_changed(self) -> None:
        self.scroll.verticalScrollBar().setValue(0)
        self._layout_timer.start()

    def _render_sections(self) -> None:
        self._layout_timer.stop()
        self.sections = group_entries(self.rows, self.search_box.text())
        count = sum(len(section.rows) for section in self.sections)
        self.count_label.setText((self.tr("%1 of %2 collected shortcuts") if self.search_box.text() else self.tr("%2 collected shortcuts")).replace("%1", str(count)).replace("%2", str(len(self.rows))))
        self.empty_panel.setVisible(not self.sections)
        self.scroll.setVisible(bool(self.sections))
        self.empty_label.setText(self.tr("No matching shortcuts") if self.rows else self.tr("No shortcuts collected for this application yet"))
        self.center_button.setVisible(not self.rows)
        while self.columns_layout.count():
            item = self.columns_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        width = max(1, self.width() - 64)
        self._last_width = width
        automatic = column_count_for_width(width)
        requested = self._debug_column_count or automatic
        # A suggested column count never forces horizontal scrolling.
        columns = min(requested, automatic)
        self.rendered_columns = balance_categories(self.sections, columns)
        for sections in self.rendered_columns:
            column = QWidget(self.content)
            column.setMinimumWidth(0)
            column.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            stack = QVBoxLayout(column)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(16)
            for section in sections:
                stack.addWidget(self._section_widget(section, column))
            stack.addStretch(1)
            self.columns_layout.addWidget(column, 1)

    def set_debug_column_count(self, count: int | None) -> None:
        """Test/developer hook; no ordinary-user control is rendered."""
        self._debug_column_count = count
        self._render_sections()

    def _section_widget(self, section, parent):
        panel = QFrame(parent)
        panel.setObjectName("guideSection")
        stack = QVBoxLayout(panel)
        stack.setContentsMargins(14, 14, 14, 12)
        stack.setSpacing(3)
        heading = QLabel(f"{section.title}   {len(section.rows)}", panel)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName("guideCategory")
        stack.addWidget(heading)
        for row in section.rows:
            widget = QFrame(panel)
            widget.setObjectName("guideRow")
            widget.setToolTip(f"{row.trigger}\n{row.description}")
            line = QHBoxLayout(widget)
            line.setContentsMargins(3, 7, 3, 7)
            line.setSpacing(10)
            key = QLabel(row.trigger, widget)
            key.setTextFormat(Qt.TextFormat.PlainText)
            key.setObjectName("guideTrigger")
            key.setWordWrap(True)
            key.setFixedWidth(116)
            line.addWidget(key, 0, Qt.AlignmentFlag.AlignTop)
            text = QLabel(row.description or row.title, widget)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.setWordWrap(True)
            text.setMinimumWidth(0)
            line.addWidget(text, 1)
            if row.source == "USER_APP" or row.entry.recommended:
                badge = QLabel(self.tr("Mine") if row.source == "USER_APP" else "★", widget)
                badge.setObjectName("guideBadge")
                badge.setToolTip(self.tr("My Shortcut") if row.source == "USER_APP" else self.tr("Recommended"))
                line.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            stack.addWidget(widget)
        return panel

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._session_open and abs(self.width() - 64 - self._last_width) > 8:
            self._layout_timer.start()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate and getattr(self, "_session_open", False):
            self.close()
        return super().event(event)

    def closeEvent(self, event) -> None:
        self._layout_timer.stop()
        if self._session_open:
            self._session_open = False
            self.snapshot = None
            self.closed.emit()
        super().closeEvent(event)
