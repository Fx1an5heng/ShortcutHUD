"""Own one explicit Guide session; keyboard truth remains in KeyboardHandler."""
import logging

from PySide6.QtCore import QObject

from .full_guide_input import ModifierTapInterpreter
from .full_guide_model import ModifierFilterState
from .full_guide_pin import FullGuidePinService
from .keypath_model import GuideMode, KeyPathSession, build_keypath_dataset
from .shortcut_catalog_resolver import CatalogShortcutResolver
from .suppression_policy import PresentationIntent

logger = logging.getLogger(__name__)


class FullGuideController(QObject):
    def __init__(self, view, quick_hud, policy, context_provider, catalog_provider, profiles_provider, language_provider, *, selection_store=None, input_service=None, parent=None) -> None:
        super().__init__(parent)
        self.view, self.quick_hud, self.policy = view, quick_hud, policy
        self.context_provider, self.catalog_provider = context_provider, catalog_provider
        self.profiles_provider, self.language_provider = profiles_provider, language_provider
        self.selection_store, self.input_service = selection_store, input_service
        self.snapshot = None
        self.active = False
        self.mode = GuideMode.NORMAL
        self.keypath_session = None
        self.modifier_filter = ModifierFilterState()
        self.input_interpreter = ModifierTapInterpreter()
        self.pin_service = None
        view.closed.connect(self._on_closed)
        view.escape_requested.connect(self.on_escape)
        view.modifier_key_event.connect(self.on_key_event)
        view.non_modifier_key_pressed.connect(self.on_non_modifier_key)
        view.focus_changed.connect(self.on_focus_changed)
        view.pin_toggled.connect(self.on_pin_toggled)
        view.keypath_enter_requested.connect(self.enter_keypath)
        view.keypath_hint_pressed.connect(self.on_keypath_hint)
        view.keypath_back_requested.connect(self.on_keypath_back)
        view.keypath_category_selected.connect(self.on_keypath_category)
        view.keypath_action_selected.connect(self.on_keypath_action)
        if input_service is not None:
            input_service.key_event.connect(self.on_key_event)

    def toggle(self) -> None:
        if self.active:
            self.close()
            return
        if not self.policy.allows(PresentationIntent.USER_INITIATED):
            return
        snapshot = self.context_provider()
        language = self.language_provider()
        catalog = self.catalog_provider()
        rows = CatalogShortcutResolver(catalog).resolve_view(snapshot.descriptor.runtime_identity, self.profiles_provider(), language)
        self.pin_service = FullGuidePinService(catalog, self.selection_store, snapshot.descriptor.runtime_identity)
        self.mode = GuideMode.NORMAL
        self.keypath_session = None
        self.modifier_filter = ModifierFilterState()
        self.input_interpreter.reset()
        self.snapshot = snapshot
        self.active = True
        self.quick_hud.set_guide_active(True)
        try:
            self.view.present(snapshot, rows, language, self.pin_service.pin_states())
        except Exception:
            self._on_closed()
            raise

    def close(self) -> None:
        self.view.close()
        self._on_closed()

    def _on_closed(self) -> None:
        if self.input_service is not None:
            self.input_service.deactivate()
        self.input_interpreter.reset()
        self.mode = GuideMode.NORMAL
        self.keypath_session = None
        self.modifier_filter = ModifierFilterState()
        self.pin_service = None
        if self.active:
            self.active = False
            self.snapshot = None
            self.quick_hud.set_guide_active(False)

    def on_key_event(self, key_name: str, event_type: str) -> None:
        if not self.active or self.mode == GuideMode.KEYPATH:
            return
        tapped = self.input_interpreter.handle(key_name, event_type)
        if tapped is None:
            return
        updated = self.modifier_filter.add(tapped)
        if updated != self.modifier_filter:
            self.modifier_filter = updated
            self.view.set_modifier_filters(updated.selected)

    def on_non_modifier_key(self) -> None:
        if self.active and self.mode == GuideMode.NORMAL:
            self.input_interpreter.handle("", "down")

    def on_escape(self) -> None:
        if not self.active:
            return
        if self.mode == GuideMode.KEYPATH:
            self.exit_keypath()
            return
        if self.modifier_filter.selected or self.view.search_box.text():
            self.input_interpreter.reset()
            self.modifier_filter = ModifierFilterState()
            self.view.clear_search()
            self.view.set_modifier_filters(())
            return
        self.close()

    def enter_keypath(self) -> None:
        if not self.active or self.mode == GuideMode.KEYPATH:
            return
        self.input_interpreter.reset()
        self.keypath_session = KeyPathSession(build_keypath_dataset(self.view.keypath_sections()))
        self.mode = GuideMode.KEYPATH
        self.view.enter_keypath(self.keypath_session)

    def exit_keypath(self) -> None:
        if self.mode != GuideMode.KEYPATH:
            return
        self.input_interpreter.reset()
        self.mode = GuideMode.NORMAL
        self.keypath_session = None
        self.view.exit_keypath()

    def on_keypath_hint(self, key: str) -> None:
        if self.mode == GuideMode.KEYPATH and self.keypath_session is not None:
            self.keypath_session.select_hint(key)
            self.view.update_keypath(self.keypath_session)

    def on_keypath_back(self) -> None:
        if self.mode == GuideMode.KEYPATH and self.keypath_session is not None:
            self.keypath_session.back()
            self.view.update_keypath(self.keypath_session)

    def on_keypath_category(self, category_key: str) -> None:
        if self.mode == GuideMode.KEYPATH and self.keypath_session is not None:
            if self.keypath_session.select_category(category_key):
                self.view.update_keypath(self.keypath_session)

    def on_keypath_action(self, entry_id: str) -> None:
        if self.mode == GuideMode.KEYPATH and self.keypath_session is not None:
            if self.keypath_session.select_action(entry_id):
                self.view.update_keypath(self.keypath_session)

    def on_focus_changed(self, focused: bool, hwnd: int) -> None:
        if self.input_service is None:
            return
        if self.active and focused:
            self.input_service.activate(hwnd)
        else:
            self.input_service.deactivate()

    def on_pin_toggled(self, entry_id: str, pinned: bool) -> None:
        if not self.active or self.mode != GuideMode.NORMAL or self.pin_service is None:
            return
        try:
            if self.pin_service.set_pinned(entry_id, pinned):
                self.view.set_pin_states(self.pin_service.pin_states())
        except Exception as error:
            logger.warning("Could not update Quick HUD selection: %s", error)

    def on_suppression_changed(self) -> None:
        if self.active and not self.policy.allows(PresentationIntent.USER_INITIATED):
            self.close()
