"""Local Qt single-step shortcut recording helpers.

The recorder is deliberately limited to key events delivered to a focused
editor.  It owns no persistence, global hook, or application shortcut data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from .modifier_state import canonicalize_modifier_state
from .shortcut_key import ShortcutKeyError, normalize_shortcut_key


class RecordingState(Enum):
    IDLE = auto()
    RECORDING = auto()


class RecordingRejection(Enum):
    """Why a candidate was not completed by Recorder v1."""

    NO_MODIFIER = auto()
    WIN = auto()
    ALTGR = auto()
    CTRL_ALT_PRINTABLE = auto()
    UNSUPPORTED_KEY = auto()


@dataclass(frozen=True, slots=True)
class RecordingResult:
    """One recorder event outcome.

    ``shortcut`` is populated only for a complete single-step result.
    ``rejection`` keeps unsupported candidates explicit so the UI can provide
    an actionable inline message without changing any editor fields.
    """

    shortcut: tuple[str, str] | None = None
    rejection: RecordingRejection | None = None


def _enum_value(value: object) -> int:
    enum_value = getattr(value, "value", value)
    return int(enum_value)


_MODIFIER_KEYS: Final[dict[int, str]] = {
    _enum_value(Qt.Key.Key_Control): "Ctrl",
    _enum_value(Qt.Key.Key_Shift): "Shift",
    _enum_value(Qt.Key.Key_Alt): "Alt",
    _enum_value(Qt.Key.Key_Meta): "Win",
    _enum_value(Qt.Key.Key_AltGr): "AltGr",
}

_SPECIAL_KEYS: Final[dict[int, str]] = {
    _enum_value(Qt.Key.Key_Tab): "Tab",
    _enum_value(Qt.Key.Key_Return): "Enter",
    _enum_value(Qt.Key.Key_Enter): "Enter",
    _enum_value(Qt.Key.Key_Escape): "Esc",
    _enum_value(Qt.Key.Key_Space): "Space",
    _enum_value(Qt.Key.Key_Backspace): "Backspace",
    _enum_value(Qt.Key.Key_Delete): "Delete",
    _enum_value(Qt.Key.Key_Insert): "Insert",
    _enum_value(Qt.Key.Key_Home): "Home",
    _enum_value(Qt.Key.Key_End): "End",
    _enum_value(Qt.Key.Key_PageUp): "PageUp",
    _enum_value(Qt.Key.Key_PageDown): "PageDown",
    _enum_value(Qt.Key.Key_Up): "Up",
    _enum_value(Qt.Key.Key_Down): "Down",
    _enum_value(Qt.Key.Key_Left): "Left",
    _enum_value(Qt.Key.Key_Right): "Right",
}

_F1 = _enum_value(Qt.Key.Key_F1)
_F24 = _enum_value(Qt.Key.Key_F24)
_KEY_UNKNOWN = _enum_value(Qt.Key.Key_unknown)

_MODIFIER_FLAG_NAMES: Final[tuple[tuple[Qt.KeyboardModifier, str], ...]] = (
    (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
    (Qt.KeyboardModifier.AltModifier, "Alt"),
    (Qt.KeyboardModifier.ShiftModifier, "Shift"),
    (Qt.KeyboardModifier.MetaModifier, "Win"),
)

_PRINTABLE_SYMBOLS: Final[frozenset[str]] = frozenset(
    "`~!@#$%^&*()-_=+[]{}\\|;:'\",.<>/?"
)

_SYSTEM_RESERVED_IDENTITIES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("Alt", "F4"),
        ("Ctrl+Shift", "Esc"),
    }
)


def modifier_tokens(event: QKeyEvent) -> set[str]:
    """Return logical modifiers exposed by the Qt event flags."""

    flags = event.modifiers()
    return {
        name
        for flag, name in _MODIFIER_FLAG_NAMES
        if flags & flag
    }


def is_explicit_altgr(event: QKeyEvent) -> bool:
    """Return only AltGr evidence Qt exposes without guessing keyboard layout."""

    return event.key() == _enum_value(Qt.Key.Key_AltGr) or bool(
        event.modifiers() & Qt.KeyboardModifier.GroupSwitchModifier
    )


def terminal_key_name(event: QKeyEvent) -> str | None:
    """Map ``QKeyEvent.key()`` to the existing canonical terminal-key system.

    ``QKeyEvent.text()`` and native virtual-key assumptions are intentionally
    ignored.  This preserves the project's existing logical symbol inventory:
    for example, a shifted slash is represented by Qt's ``?`` key and stored
    as ``?`` just like the manual editor input.
    """

    key = int(event.key())
    if key in _MODIFIER_KEYS or key in (0, _KEY_UNKNOWN):
        return None
    if key in _SPECIAL_KEYS:
        candidate = _SPECIAL_KEYS[key]
    elif _F1 <= key <= _F24:
        candidate = f"F{key - _F1 + 1}"
    elif ord("A") <= key <= ord("Z"):
        candidate = chr(key)
    elif ord("0") <= key <= ord("9"):
        candidate = chr(key)
    elif 0x20 <= key <= 0x7E:
        candidate = chr(key)
    else:
        return None

    try:
        return normalize_shortcut_key(candidate)
    except ShortcutKeyError:
        return None


def _is_ctrl_alt_printable(key: str) -> bool:
    return len(key) == 1 and (key.isalnum() or key in _PRINTABLE_SYMBOLS)


class ShortcutRecorder:
    """Stateful, one-result recorder for a focused Qt editor.

    The caller owns the temporary Qt event filter.  This class only consumes
    key events passed to it and immediately returns to ``IDLE`` after success.
    """

    def __init__(self) -> None:
        self._state = RecordingState.IDLE
        self._active_modifiers: set[str] = set()
        self._altgr_active = False

    @property
    def state(self) -> RecordingState:
        return self._state

    @property
    def active_modifiers(self) -> frozenset[str]:
        return frozenset(self._active_modifiers)

    def start(self) -> bool:
        if self._state is RecordingState.RECORDING:
            return False
        self._state = RecordingState.RECORDING
        self._active_modifiers.clear()
        self._altgr_active = False
        return True

    def cancel(self) -> None:
        self._state = RecordingState.IDLE
        self._active_modifiers.clear()
        self._altgr_active = False

    def handle_event(self, event: QKeyEvent) -> RecordingResult | None:
        """Handle one local Qt key event, if recording is active."""

        if self._state is not RecordingState.RECORDING:
            return None
        if event.type() == QEvent.Type.KeyRelease:
            self._handle_key_release(event)
            return None
        if event.type() != QEvent.Type.KeyPress or event.isAutoRepeat():
            return None

        if is_explicit_altgr(event):
            self._altgr_active = True
            return RecordingResult(rejection=RecordingRejection.ALTGR)

        modifier_key = _MODIFIER_KEYS.get(int(event.key()))
        if modifier_key is not None:
            if modifier_key == "AltGr":
                self._altgr_active = True
                return RecordingResult(rejection=RecordingRejection.ALTGR)
            self._active_modifiers.add(modifier_key)
            return None

        if self._altgr_active:
            return RecordingResult(rejection=RecordingRejection.ALTGR)

        active_modifiers = self._active_modifiers | modifier_tokens(event)
        canonical_modifier = canonicalize_modifier_state(active_modifiers)
        key = terminal_key_name(event)
        if key is None:
            return RecordingResult(rejection=RecordingRejection.UNSUPPORTED_KEY)
        if canonical_modifier is None:
            return RecordingResult(rejection=RecordingRejection.NO_MODIFIER)
        if "Win" in active_modifiers:
            return RecordingResult(rejection=RecordingRejection.WIN)
        if (
            {"Ctrl", "Alt"}.issubset(active_modifiers)
            and _is_ctrl_alt_printable(key)
        ):
            return RecordingResult(
                rejection=RecordingRejection.CTRL_ALT_PRINTABLE
            )
        if (canonical_modifier, key) in _SYSTEM_RESERVED_IDENTITIES:
            return RecordingResult(rejection=RecordingRejection.UNSUPPORTED_KEY)

        self._state = RecordingState.IDLE
        self._active_modifiers.clear()
        self._altgr_active = False
        return RecordingResult(shortcut=(canonical_modifier, key))

    def _handle_key_release(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        modifier_key = _MODIFIER_KEYS.get(int(event.key()))
        if modifier_key == "AltGr":
            self._altgr_active = False
        elif modifier_key is not None:
            self._active_modifiers.discard(modifier_key)
