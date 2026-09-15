"""Large, focus-owning, read-only shortcut reference built with Qt Widgets."""
from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .full_guide_context import guide_geometry
from .full_guide_model import balance_categories, group_entries, plan_guide_layout
from .keypath_view import KeyPathPanel


class _ElidedLabel(QLabel):
    """Single-line label whose tooltip retains the complete presentation text."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setToolTip(text)
        self._update_elide()

    @property
    def full_text(self) -> str:
        return self._full_text

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(min(hint.width(), 240), hint.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elide()

    def _update_elide(self) -> None:
        width = max(1, self.contentsRect().width())
        super().setText(self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, width))


class _PinLabel(QLabel):
    clicked = Signal()

    def __init__(self, pinned: bool, parent=None) -> None:
        super().__init__(parent)
        self._pinned = pinned
        self._row_hovered = False
        self.setFixedWidth(22)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._update_display()

    def set_row_hovered(self, hovered: bool) -> None:
        self._row_hovered = hovered
        self._update_display()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._update_display()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._update_display()

    def _update_display(self) -> None:
        self.setText("★" if self._pinned else "☆" if self._row_hovered or self.hasFocus() else "")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _ModeLinkLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _GuideRow(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.pin_label = None

    def enterEvent(self, event) -> None:
        if self.pin_label is not None:
            self.pin_label.set_row_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.pin_label is not None:
            self.pin_label.set_row_hovered(False)
        super().leaveEvent(event)


class FullGuideWindow(QWidget):
    closed = Signal()
    center_requested = Signal()
    escape_requested = Signal()
    modifier_key_event = Signal(str, str)
    non_modifier_key_pressed = Signal()
    focus_changed = Signal(bool, int)
    pin_toggled = Signal(str, bool)
    keypath_enter_requested = Signal()
    keypath_hint_pressed = Signal(str)
    keypath_back_requested = Signal()
    keypath_category_selected = Signal(str)
    keypath_action_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("FullGuideWindow")
        self.setWindowTitle(self.tr("Full Guide"))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._session_open = False
        self._keypath_active = False
        self._normal_scroll_value = 0
        self.snapshot = None
        self.rows = ()
        self.sections = ()
        self.rendered_columns = ()
        self._modifier_filters = ()
        self._pin_states = {}
        self._density = None
        self._debug_column_count = None
        self._last_width = 0
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(35)
        self._layout_timer.timeout.connect(self._render_sections)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 10)
        layout.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(14)
        identity = QVBoxLayout()
        identity.setSpacing(2)
        self.app_label = QLabel(self)
        self.app_label.setObjectName("guideApplication")
        self.app_label.setTextFormat(Qt.TextFormat.PlainText)
        self.count_label = QLabel(self)
        self.count_label.setObjectName("guideCount")
        self.modifier_label = QLabel(self)
        self.modifier_label.setObjectName("guideModifiers")
        self.modifier_label.hide()
        self.keypath_entry = _ModeLinkLabel(self.tr("Path navigation"), self)
        self.keypath_entry.setObjectName("guideKeyPathEntry")
        self.keypath_entry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keypath_entry.setToolTip(self.tr("Press Tab to navigate by path"))
        self.keypath_entry.clicked.connect(self.keypath_enter_requested)
        self.keypath_status = QLabel(self)
        self.keypath_status.setObjectName("guideKeyPathStatus")
        self.keypath_status.hide()
        identity_meta = QHBoxLayout()
        identity_meta.setSpacing(10)
        identity.addWidget(self.app_label)
        identity_meta.addWidget(self.count_label)
        identity_meta.addWidget(self.modifier_label)
        identity_meta.addWidget(self.keypath_entry)
        identity_meta.addWidget(self.keypath_status)
        identity_meta.addStretch(1)
        identity.addLayout(identity_meta)
        top.addLayout(identity, 2)
        self.search_box = QLineEdit(self)
        self.search_box.setObjectName("guideSearch")
        self.search_box.setPlaceholderText(self.tr("Search shortcuts…"))
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(170)
        self.search_box.installEventFilter(self)
        top.addWidget(self.search_box, 2)
        self.close_button = QPushButton("×", self)
        self.close_button.setObjectName("guideClose")
        self.close_button.setAccessibleName(self.tr("Close"))
        self.close_button.setToolTip(self.tr("Close"))
        self.close_button.installEventFilter(self)
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
        self.center_button.installEventFilter(self)
        self.center_button.clicked.connect(self._open_center)
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_label)
        empty_layout.addWidget(self.center_button, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_layout.addStretch()
        layout.addWidget(self.empty_panel, 1)
        self.keypath_panel = KeyPathPanel(self)
        self.keypath_panel.hide()
        self.keypath_panel.category_selected.connect(self.keypath_category_selected)
        self.keypath_panel.action_selected.connect(self.keypath_action_selected)
        layout.addWidget(self.keypath_panel, 1)
        self.footer = QLabel(self.tr("Tab  Path navigation     Tap Ctrl / Alt / Shift / Win to filter     Esc  Clear filters / Close     ★  Quick HUD pin"), self)
        self.footer.setObjectName("guideFooter")
        layout.addWidget(self.footer)
        self.search_box.textChanged.connect(self._search_changed)
        self._find = QShortcut(QKeySequence("Ctrl+F"), self)
        self._find.activated.connect(self._focus_search)
        self._escape = QShortcut(QKeySequence("Esc"), self)
        self._escape.activated.connect(self.escape)
        self.setStyleSheet("""
            QWidget#FullGuideWindow { background: #20232e; border: none; }
            QWidget#guideContent { background: #20232e; }
            QLabel { color: #dce2ed; background: transparent; font-size: 13px; }
            QLabel#guideApplication { color: #f4f7fc; font-size: 26px; font-weight: 600; }
            QLabel#guideCount, QLabel#guideFooter { color: #808ba0; font-size: 11px; }
            QLabel#guideModifiers { color: #a9c9f3; font-size: 12px; font-weight: 600; }
            QLabel#guideKeyPathEntry { color: #8298b5; font-size: 11px; text-decoration: underline; }
            QLabel#guideKeyPathEntry:hover { color: #b8d8ff; }
            QLabel#guideKeyPathStatus { color: #a9c9f3; font-size: 12px; font-weight: 600; }
            QLineEdit#guideSearch { color: #edf2fa; background: #2b3040; border: 1px solid #4b5670;
                border-radius: 8px; padding: 9px 13px; font-size: 14px; }
            QLineEdit#guideSearch:focus { border-color: #91b6ec; }
            QPushButton { color: #dce2ed; background: #303747; border: 1px solid #485269;
                border-radius: 6px; padding: 8px 12px; }
            QPushButton:hover { background: #46536b; }
            QPushButton#guideClose { font-size: 24px; padding: 2px 12px; border: none; background: transparent; }
            QLabel#guidePin { color: #938463; border: none; background: transparent; font-size: 14px; }
            QLabel#guidePin:focus { color: #c3aa72; background: #303747; border-radius: 3px; }
            QFrame#guideSection { background: transparent; border: none; border-radius: 0px; }
            QLabel#guideCategory { color: #9fc4f4; font-size: 14px; font-weight: 600;
                border-bottom: 1px solid #343b49; padding: 0px 2px 5px 2px; }
            QFrame#guideRow { background: transparent; border: none; }
            QFrame#guideRow:hover { background: #2a303d; border-radius: 3px; }
            QLabel#guideTrigger { color: #b8cff3; font-size: 12px; font-weight: 600; }
            QLabel#guideDescription { color: #d3d9e3; font-size: 12px; }
            QLabel#guideBadge { color: #a99468; font-size: 11px; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: #20232e; width: 8px; }
            QScrollBar::handle:vertical { background: #55617a; border-radius: 4px; min-height: 28px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

    def present(self, snapshot, rows, language=None, pin_states=None) -> None:
        self.snapshot, self.rows = snapshot, tuple(rows)
        self._keypath_active = False
        self._normal_scroll_value = 0
        self._modifier_filters = ()
        self._pin_states = dict(pin_states or {})
        self.app_label.setText(snapshot.descriptor.display_name)
        self.search_box.blockSignals(True)
        self.search_box.clear()
        self.search_box.blockSignals(False)
        self.search_box.setEnabled(True)
        self._find.setEnabled(True)
        self.keypath_entry.show()
        self.keypath_status.hide()
        self.keypath_panel.hide()
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
            self.keypath_entry.setText(self.tr("Path navigation"))
            self.keypath_entry.setToolTip(self.tr("Press Tab to navigate by path"))
            self.footer.setText(self._keypath_footer() if self._keypath_active else self._normal_footer())
            if self._keypath_active and self.keypath_panel.session is not None:
                self._render_keypath(self.keypath_panel.session)
            self._render_sections()
        super().changeEvent(event)

    def _focus_search(self) -> None:
        self.non_modifier_key_pressed.emit()
        self.search_box.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_box.selectAll()

    def escape(self) -> None:
        self.escape_requested.emit()

    def clear_search(self) -> None:
        self.search_box.clear()

    def keypath_sections(self):
        """Return sections matching the latest query even if layout debounce is pending."""

        if self._layout_timer.isActive():
            self._render_sections()
        return self.sections

    def enter_keypath(self, session) -> None:
        if self._keypath_active:
            return
        self._normal_scroll_value = self.scroll.verticalScrollBar().value()
        self._keypath_active = True
        self.scroll.hide()
        self.empty_panel.hide()
        self.search_box.setEnabled(False)
        self._find.setEnabled(False)
        self.keypath_entry.hide()
        self.keypath_status.show()
        self.keypath_panel.show()
        self._render_keypath(session)
        self.footer.setText(self._keypath_footer())
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def update_keypath(self, session) -> None:
        if self._keypath_active:
            self._render_keypath(session)

    def exit_keypath(self) -> None:
        if not self._keypath_active:
            return
        self._keypath_active = False
        self.keypath_panel.hide()
        self.keypath_status.hide()
        self.keypath_entry.show()
        self.search_box.setEnabled(True)
        self._find.setEnabled(True)
        self.scroll.setVisible(bool(self.sections))
        self.empty_panel.setVisible(not self.sections)
        self.footer.setText(self._normal_footer())
        scroll_value = self._normal_scroll_value
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(scroll_value))
        self.search_box.setFocus(Qt.FocusReason.OtherFocusReason)

    def _render_keypath(self, session) -> None:
        self.keypath_panel.render_session(session)
        path = " → ".join((*session.path_hints, session.input_buffer) if session.input_buffer else session.path_hints)
        self.keypath_status.setText(self.tr("Path navigation") + (f"   {path}" if path else ""))

    def _normal_footer(self) -> str:
        return self.tr("Tab  Path navigation     Tap Ctrl / Alt / Shift / Win to filter     Esc  Clear filters / Close     ★  Quick HUD pin")

    def _keypath_footer(self) -> str:
        return self.tr("Backspace  Back     Esc  Exit path navigation")

    def set_modifier_filters(self, modifiers) -> None:
        self._modifier_filters = tuple(modifiers)
        self.modifier_label.setText("  ".join(f"[{modifier}]" for modifier in self._modifier_filters))
        self.modifier_label.setVisible(bool(self._modifier_filters))
        self.scroll.verticalScrollBar().setValue(0)
        self._render_sections()

    def set_pin_states(self, states) -> None:
        self._pin_states = dict(states)
        self._render_sections()

    def _open_center(self) -> None:
        self.close()
        self.center_requested.emit()

    def _search_changed(self) -> None:
        self.scroll.verticalScrollBar().setValue(0)
        self._layout_timer.start()

    def _render_sections(self) -> None:
        self._layout_timer.stop()
        self.sections = group_entries(self.rows, self.search_box.text(), self._modifier_filters)
        count = sum(len(section.rows) for section in self.sections)
        constrained = bool(self.search_box.text() or self._modifier_filters)
        self.count_label.setText((self.tr("%1 of %2 collected shortcuts") if constrained else self.tr("%2 collected shortcuts")).replace("%1", str(count)).replace("%2", str(len(self.rows))))
        self.empty_panel.setVisible(not self.sections and not self._keypath_active)
        self.scroll.setVisible(bool(self.sections) and not self._keypath_active)
        self.empty_label.setText(self.tr("No matching shortcuts") if self.rows else self.tr("No shortcuts collected for this application yet"))
        self.center_button.setVisible(not self.rows)
        while self.columns_layout.count():
            item = self.columns_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        width = max(1, self.width() - 52)
        self._last_width = width
        self._density = plan_guide_layout(self.sections, width, self.height())
        automatic = self._density.columns
        requested = self._debug_column_count or automatic
        # A suggested column count never forces horizontal scrolling.
        columns = min(requested, automatic)
        self.rendered_columns = self._density.assignments if columns == automatic else balance_categories(self.sections, columns)
        for sections in self.rendered_columns:
            column = QWidget(self.content)
            column.setMinimumWidth(0)
            column.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            stack = QVBoxLayout(column)
            stack.setContentsMargins(0, 0, 0, 0)
            stack.setSpacing(18)
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
        stack.setContentsMargins(2, 0, 2, 0)
        stack.setSpacing(2)
        heading = QLabel(f"{section.title}   {len(section.rows)}", panel)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName("guideCategory")
        stack.addWidget(heading)
        for row in section.rows:
            widget = _GuideRow(panel)
            widget.setObjectName("guideRow")
            widget.setToolTip(f"{row.trigger}\n{row.description}")
            widget.setFixedHeight(30)
            line = QHBoxLayout(widget)
            line.setContentsMargins(3, 3, 3, 3)
            line.setSpacing(9)
            key = _ElidedLabel(row.trigger, widget)
            key.setObjectName("guideTrigger")
            key.setFixedWidth(116)
            line.addWidget(key)
            text = _ElidedLabel(row.description or row.title, widget)
            text.setObjectName("guideDescription")
            text.setMinimumWidth(0)
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            line.addWidget(text, 1)
            if row.entry.id in self._pin_states:
                pinned = self._pin_states[row.entry.id]
                badge = _PinLabel(pinned, widget)
                badge.setObjectName("guidePin")
                badge.setAccessibleName(self.tr("Remove from Quick HUD") if pinned else self.tr("Add to Quick HUD"))
                badge.setToolTip(badge.accessibleName())
                badge.setCursor(Qt.CursorShape.PointingHandCursor)
                badge.installEventFilter(self)
                badge.clicked.connect(lambda entry_id=row.entry.id, desired=not pinned: self.pin_toggled.emit(entry_id, desired))
                widget.pin_label = badge
                line.addWidget(badge)
            elif row.source == "USER_APP":
                badge = QLabel(self.tr("Mine"), widget)
                badge.setObjectName("guideBadge")
                badge.setToolTip(self.tr("My Shortcut"))
                line.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            stack.addWidget(widget)
        return panel

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._session_open and abs(self.width() - 52 - self._last_width) > 8:
            self._layout_timer.start()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowActivate and getattr(self, "_session_open", False):
            self.focus_changed.emit(True, int(self.winId()))
        if event.type() == QEvent.Type.WindowDeactivate and getattr(self, "_session_open", False):
            self.focus_changed.emit(False, int(self.winId()))
            self.close()
        return super().event(event)

    def eventFilter(self, watched, event) -> bool:
        if self._session_open and self._keypath_active and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.key() == Qt.Key.Key_Escape:
                return super().eventFilter(watched, event)
            return self._handle_keypath_key_event(event)
        if self._session_open and self.isActiveWindow() and event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Tab and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                self.keypath_enter_requested.emit()
                return True
            key_names = {
                Qt.Key.Key_Control: "Ctrl", Qt.Key.Key_Alt: "Alt",
                Qt.Key.Key_Shift: "Shift",
            }
            key_name = key_names.get(event.key())
            event_type = "down" if event.type() == QEvent.Type.KeyPress else "up"
            if key_name:
                if not event.isAutoRepeat():
                    self.modifier_key_event.emit(key_name, event_type)
                return False
            if event_type == "down" and not event.isAutoRepeat():
                self.non_modifier_key_pressed.emit()
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if self._session_open and self._keypath_active and event.key() != Qt.Key.Key_Escape:
            self._handle_keypath_key_event(event)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if self._session_open and self._keypath_active:
            event.accept()
            return
        super().keyReleaseEvent(event)

    def _handle_keypath_key_event(self, event) -> bool:
        if event.type() == QEvent.Type.KeyRelease or event.isAutoRepeat():
            event.accept()
            return True
        if event.key() == Qt.Key.Key_Backspace:
            self.keypath_back_requested.emit()
        elif Qt.Key.Key_A <= event.key() <= Qt.Key.Key_Z:
            self.keypath_hint_pressed.emit(chr(ord("A") + event.key() - Qt.Key.Key_A))
        elif Qt.Key.Key_0 <= event.key() <= Qt.Key.Key_9:
            self.keypath_hint_pressed.emit(chr(ord("0") + event.key() - Qt.Key.Key_0))
        event.accept()
        return True

    def closeEvent(self, event) -> None:
        self._layout_timer.stop()
        if self._session_open:
            self._session_open = False
            self.focus_changed.emit(False, int(self.winId()))
            self.snapshot = None
            self._keypath_active = False
            self._normal_scroll_value = 0
            self._modifier_filters = ()
            self._pin_states = {}
            self.closed.emit()
        super().closeEvent(event)
