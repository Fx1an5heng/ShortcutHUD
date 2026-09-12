"""User-initiated hotkey configuration; startup never writes a default."""
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QKeySequenceEdit, QLabel, QPushButton, QVBoxLayout

from .full_guide_hotkey import DEFAULT_GUIDE_HOTKEY


class FullGuideSettingsDialog(QDialog):
    def __init__(self, current: str, apply_hotkey, error: str = "", parent=None) -> None:
        super().__init__(parent)
        self.apply_hotkey = apply_hotkey
        self.setWindowTitle(self.tr("Full Guide shortcut"))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        label = QLabel(self.tr("Press once to open the current app's Guide; press again to close."), self)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.editor = QKeySequenceEdit(QKeySequence(current if isinstance(current, str) else DEFAULT_GUIDE_HOTKEY), self)
        self.editor.setMaximumSequenceLength(1)
        layout.addWidget(self.editor)
        hint = QLabel(self.tr("Use Ctrl, Alt or Shift with a letter, number, F-key (except F12), or navigation key. Windows-reserved shortcuts are unavailable."), self)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        if error:
            self.status.setText(self.tr("Shortcut unavailable. Choose another combination.") + "\n" + error)
        layout.addWidget(self.status)
        default = QPushButton(self.tr("Use default: %1").replace("%1", DEFAULT_GUIDE_HOTKEY), self)
        default.clicked.connect(lambda: self.editor.setKeySequence(QKeySequence(DEFAULT_GUIDE_HOTKEY)))
        layout.addWidget(default)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self) -> None:
        text = self.editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        success, detail = self.apply_hotkey(text)
        if success:
            self.accept()
        else:
            self.status.setText(self.tr("Shortcut unavailable. Choose another combination.") + "\n" + detail)
