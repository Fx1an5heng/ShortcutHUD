"""Own one explicit Guide session; keyboard truth remains in KeyboardHandler."""
from PySide6.QtCore import QObject

from .shortcut_catalog_resolver import CatalogShortcutResolver
from .suppression_policy import PresentationIntent


class FullGuideController(QObject):
    def __init__(self, view, quick_hud, policy, context_provider, catalog_provider, profiles_provider, language_provider, parent=None) -> None:
        super().__init__(parent)
        self.view, self.quick_hud, self.policy = view, quick_hud, policy
        self.context_provider, self.catalog_provider = context_provider, catalog_provider
        self.profiles_provider, self.language_provider = profiles_provider, language_provider
        self.snapshot = None
        self.active = False
        view.closed.connect(self._on_closed)

    def toggle(self) -> None:
        if self.active:
            self.close()
            return
        if not self.policy.allows(PresentationIntent.USER_INITIATED):
            return
        snapshot = self.context_provider()
        language = self.language_provider()
        rows = CatalogShortcutResolver(self.catalog_provider()).resolve_view(snapshot.descriptor.runtime_identity, self.profiles_provider(), language)
        self.snapshot = snapshot
        self.active = True
        self.quick_hud.set_guide_active(True)
        try:
            self.view.present(snapshot, rows, language)
        except Exception:
            self._on_closed()
            raise

    def close(self) -> None:
        self.view.close()
        self._on_closed()

    def _on_closed(self) -> None:
        if self.active:
            self.active = False
            self.snapshot = None
            self.quick_hud.set_guide_active(False)

    def on_suppression_changed(self) -> None:
        if self.active and not self.policy.allows(PresentationIntent.USER_INITIATED):
            self.close()
