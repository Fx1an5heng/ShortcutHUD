# shortcut_overlay/keyboard_handler.py
"""
Handles global keyboard event listening and processing.

This module uses the 'keyboard' library to capture system-wide key presses
and releases. It normalizes key names, tracks modifier states (Ctrl, Shift, Alt, Win),
and emits signals for key events and modifier changes. It also includes a
mechanism to detect "stuck" keys if the 'keyboard' library misses an 'up' event.
"""
import keyboard  # type: ignore # 'keyboard' library might not have type stubs.
from PySide6.QtCore import QObject, Qt, Signal, Slot, QTimer
import threading
import time
from typing import Set, Dict, Optional, Any

from .input_state_reconciler import PhysicalModifierReconciler

# Type alias for the event object from the 'keyboard' library.
# Using 'Any' as the 'keyboard' library lacks official type stubs.
KeyboardEvent = Any
_WINDOWS_KEY_VKS = frozenset((0x5B, 0x5C))
_NORMALIZED_MODIFIER_NAMES = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
}


class KeyboardHandler(QObject):
    """
    Listens for global keyboard events, normalizes them, and signals them
    to other application components for UI updates or other actions.
    Tracks active modifiers and handles potentially "stuck" keys.
    """

    # Signal emitted on any key press or release.
    # Args: (normalized_key_name: str, event_type: str ("up" or "down")).
    key_event_signal = Signal(str, str)

    # Signal emitted when the set of active logical modifiers (Ctrl, Shift, Alt, Win) changes.
    # Args: (active_modifiers_set: set of lowercase modifier names, e.g., {"ctrl", "shift"}).
    modifiers_changed = Signal(set)

    # Hook callbacks run outside the Qt thread. Timer lifecycle changes are
    # therefore queued back to this QObject's thread.
    _state_check_sync_requested = Signal()

    # Signal for exiting the application (currently not used as exit is via tray menu).
    # exit_signal = Signal() # Kept if future use is intended, otherwise can be removed.

    # Timeout in milliseconds to consider a key "stuck" if no 'up' event is received.
    DEFAULT_KEY_TIMEOUT_MS: int = 250
    # Interval in milliseconds for the timer that checks for stuck key states.
    STATE_CHECK_INTERVAL_MS: int = 100

    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        modifier_reconciler: PhysicalModifierReconciler | None = None,
    ):
        """
        Initializes the KeyboardHandler.

        Sets up internal state for tracking pressed keys, active modifiers,
        and a timer for checking stuck keys.

        Args:
            parent: The parent QObject, if any.
        """
        super().__init__(parent)
        self._state_lock = threading.RLock()
        # Stores lowercase base names of active modifiers: "ctrl", "shift", "alt", "win".
        self._active_modifiers: Set[str] = set()
        self._modifier_state_revision: int = 0
        self._modifier_reconciler = (
            modifier_reconciler or PhysicalModifierReconciler()
        )
        self._hooked: bool = (
            False  # Flag indicating if the global keyboard hook is active.
        )
        # Stores normalized key names and their press timestamps (milliseconds since epoch).
        self._pressed_keys: Dict[str, float] = {}
        self._key_timeout_ms: int = self.DEFAULT_KEY_TIMEOUT_MS

        # Timer to periodically check for keys that might have missed their 'up' event.
        self._state_check_timer: QTimer = QTimer(self)
        self._state_check_timer.timeout.connect(self._check_key_states)
        self._state_check_timer.setInterval(self.STATE_CHECK_INTERVAL_MS)
        self._state_check_sync_requested.connect(
            self._sync_state_check_timer,
            type=Qt.ConnectionType.QueuedConnection,
        )

    @Slot(int)
    def reconcile_win_release(self, vk: int) -> None:
        """Reconcile a physical Win-up consumed by the Win input proxy.

        The caller reaches this slot through a queued Qt signal, so the hook
        thread never touches QObject consumers or HUD state directly. The
        update is idempotent and does not synthesize any keyboard input.
        """

        if vk not in _WINDOWS_KEY_VKS:
            return

        self._reconcile_modifier_state(only={"win"})

    def _normalize_key_name(self, name_from_lib: Optional[str]) -> Optional[str]:
        """
        Normalizes key names received from the 'keyboard' library into a
        standardized format used throughout the application.
        For example, "left ctrl" becomes "Ctrl", "a" becomes "A", "esc" becomes "Esc".

        Args:
            name_from_lib: The raw key name string from the 'keyboard' library.

        Returns:
            The normalized key name string, or None if the input is invalid or cannot be normalized.
        """
        if not name_from_lib:
            return None
        name_lower = (
            name_from_lib.lower()
        )  # Normalize to lowercase for easier matching.

        # Check for modifier keys first, as they can have side variations (e.g., "left shift").
        if "ctrl" in name_lower:
            return "Ctrl"
        if "shift" in name_lower:
            return "Shift"
        if "alt" in name_lower:
            return "Alt"  # Catches "alt" and "alt gr".
        if "win" in name_lower or "cmd" in name_lower or name_lower == "meta":
            return "Win"  # Windows/Command/Meta key.

        # Normalize function keys (F1-F24).
        if (
            name_lower.startswith("f")
            and len(name_lower) > 1
            and name_lower[1:].isdigit()
        ):
            num = int(name_lower[1:])
            if 1 <= num <= 24:
                return f"F{num}"

        # Map common special key names to their normalized forms.
        special_keys_map: Dict[str, str] = {
            "escape": "Esc",
            "esc": "Esc",
            "space": "Space",
            "space bar": "Space",
            "enter": "Enter",
            "return": "Enter",
            "backspace": "Backspace",
            "caps lock": "Caps Lock",
            "capslock": "Caps Lock",
            "tab": "Tab",
            "delete": "Del",
            "del": "Del",
            "home": "Home",
            "end": "End",
            "page up": "PgUp",
            "pgup": "PgUp",
            "page down": "PgDn",
            "pgdn": "PgDn",
            "insert": "Ins",
            "ins": "Ins",
            "print screen": "PrtSc",
            "printscr": "PrtSc",
            "scroll lock": "ScrLk",
            "scrolllock": "ScrLk",
            "pause": "Pause",
            "pause break": "Pause",
            "up": "↑",
            "down": "↓",
            "left": "←",
            "right": "→",  # Arrow keys.
            "menu": "Menu",
            "apps": "Menu",
            "application": "Menu",  # Context menu key.
            "decimal": ".",
            "numpad decimal": ".",
            "separator": ",",
        }
        if name_lower in special_keys_map:
            return special_keys_map[name_lower]

        # Map common symbol names and their character representations.
        symbol_map: Dict[str, str] = {
            ";": ";",
            ":": ":",
            "semicolon": ";",
            "=": "=",
            "equals": "=",
            ",": ",",
            "comma": ",",
            "-": "-",
            "minus": "-",
            "subtract": "-",
            "hyphen": "-",
            ".": ".",
            "period": ".",
            "dot": ".",
            "/": "/",
            "slash": "/",
            "forward slash": "/",
            "divide": "/",
            "`": "`",
            "backtick": "`",
            "grave accent": "`",
            "[": "[",
            "open bracket": "[",
            "left bracket": "[",
            "]": "]",
            "close bracket": "]",
            "right bracket": "]",
            "\\": "\\",
            "backslash": "\\",
            "back slash": "\\",
            "'": "'",
            "apostrophe": "'",
            "single quote": "'",
            "*": "*",
            "multiply": "*",
            "asterisk": "*",
            "numpad multiply": "*",
            "+": "+",
            "add": "+",
            "plus": "+",
            "numpad plus": "+",
        }
        if name_lower in symbol_map:
            return symbol_map[name_lower]

        # Handle single character keys (letters are uppercased, digits/symbols as is).
        if len(name_lower) == 1:
            if name_lower.isalpha():
                return name_lower.upper()
            return name_lower  # For digits and symbols not caught by symbol_map.

        # Fallback: Uppercase the original name if no specific rule matched.
        # This might lead to inconsistent names for unmapped special keys.
        return name_from_lib.upper()

    def _get_modifier_base_name(self, normalized_key: str) -> Optional[str]:
        """
        Converts a normalized modifier key name (e.g., "Ctrl") to its lowercase base
        name (e.g., "ctrl") for internal state tracking.

        Args:
            normalized_key: The normalized key name.

        Returns:
            The lowercase base modifier name ("ctrl", "shift", "alt", "win"),
            or None if the key is not a recognized modifier.
        """
        if normalized_key == "Ctrl":
            return "ctrl"
        if normalized_key == "Shift":
            return "shift"
        if normalized_key == "Alt":
            return "alt"
        if normalized_key == "Win":
            return "win"
        return None

    def _map_normalized_to_keyboard_lib_name(self, normalized_key_name: str) -> str:
        """
        Maps an application-normalized key name back to a name format that the
        'keyboard' library's `is_pressed()` function is likely to recognize.
        This is primarily for checking key states with `keyboard.is_pressed()`.

        Args:
            normalized_key_name: The application's internal normalized key name.

        Returns:
            A key name string suitable for `keyboard.is_pressed()`.
        """
        # Map specific normalized names back to common library names.
        if normalized_key_name == "Ctrl":
            return "ctrl"
        if normalized_key_name == "Shift":
            return "shift"
        if normalized_key_name == "Alt":
            return "alt"
        if normalized_key_name == "Win":
            return "windows"  # 'keyboard' often uses "windows".
        if normalized_key_name == "Caps Lock":
            return "caps lock"
        if normalized_key_name == "PrtSc":
            return "print screen"
        if normalized_key_name == "ScrLk":
            return "scroll lock"
        if normalized_key_name == "PgUp":
            return "page up"
        if normalized_key_name == "PgDn":
            return "page down"
        # For most other keys, their lowercase version is usually sufficient for the library.
        return normalized_key_name.lower()

    def _check_key_states(self) -> None:
        """
        Periodically called by `_state_check_timer`.
        Checks if keys recorded as pressed are still physically pressed according
        to the 'keyboard' library. If a key is no longer pressed but its 'up'
        event was missed, this method simulates a release event.
        """
        current_time_ms = time.time() * 1000
        keys_to_release_simulated: Set[str] = set()

        # Iterate over a copy of _pressed_keys items as the dictionary might be modified.
        with self._state_lock:
            pressed_keys = list(self._pressed_keys.items())
        for key_name, press_time_ms in pressed_keys:
            # Modifier recovery must use a physical source independent of the
            # hook-backed state used by keyboard.is_pressed().
            if self._get_modifier_base_name(key_name) is not None:
                continue
            try:
                lib_key_name = self._map_normalized_to_keyboard_lib_name(key_name)
                if not keyboard.is_pressed(lib_key_name):
                    # Key is no longer pressed according to the library.
                    keys_to_release_simulated.add(key_name)
            except Exception:  # Catch errors from keyboard.is_pressed()
                # If checking state fails, fall back to timeout logic for this key.
                if current_time_ms - press_time_ms > self._key_timeout_ms:
                    keys_to_release_simulated.add(key_name)

        for key_name_to_release in keys_to_release_simulated:
            self._simulate_key_release(key_name_to_release)

        self._reconcile_modifier_state()
        self._sync_state_check_timer()

    def _reconcile_modifier_state(
        self,
        *,
        only: Set[str] | None = None,
    ) -> None:
        """Apply one physical reconciliation through the normal signal chain."""

        with self._state_lock:
            previous = self._active_modifiers.copy()
            revision = self._modifier_state_revision

        reconciled = self._modifier_reconciler.reconcile(previous, only=only)
        if reconciled == previous:
            self._sync_state_check_timer()
            return

        with self._state_lock:
            # A hook event observed during the physical read owns the newer
            # state. The next timer pass will reconcile that fresh snapshot.
            if (
                self._modifier_state_revision != revision
                or self._active_modifiers != previous
            ):
                self._sync_state_check_timer()
                return

            removed = previous.difference(reconciled)
            self._active_modifiers = reconciled
            self._modifier_state_revision += 1
            for modifier in removed:
                normalized_name = _NORMALIZED_MODIFIER_NAMES.get(modifier)
                if normalized_name is not None:
                    self._pressed_keys.pop(normalized_name, None)
            active_modifiers = self._active_modifiers.copy()

        for modifier in _NORMALIZED_MODIFIER_NAMES:
            if modifier in removed:
                self.key_event_signal.emit(
                    _NORMALIZED_MODIFIER_NAMES[modifier],
                    "up",
                )
        self.modifiers_changed.emit(active_modifiers)
        self._sync_state_check_timer()

    @Slot()
    def _sync_state_check_timer(self) -> None:
        """Run the watchdog only while the handler owns non-idle state."""

        with self._state_lock:
            should_run = self._hooked and bool(self._active_modifiers)

        if should_run and not self._state_check_timer.isActive():
            self._state_check_timer.start()
        elif not should_run and self._state_check_timer.isActive():
            self._state_check_timer.stop()

    def _simulate_key_release(self, key_name: str) -> None:
        """
        Simulates a key release event for a key presumed to be "stuck".
        Updates internal state and emits `key_event_signal` and potentially
        `modifiers_changed` if it was a modifier.

        Args:
            key_name: The normalized name of the key to simulate a release for.
        """
        active_modifiers = None
        with self._state_lock:
            if key_name not in self._pressed_keys:
                return
            del self._pressed_keys[key_name]

            modifier_base = self._get_modifier_base_name(key_name)
            if modifier_base and modifier_base in self._active_modifiers:
                # This fallback treats a timed-out modifier as released.
                self._active_modifiers.discard(modifier_base)
                self._modifier_state_revision += 1
                active_modifiers = self._active_modifiers.copy()

        self.key_event_signal.emit(key_name, "up")
        if active_modifiers is not None:
            self.modifiers_changed.emit(active_modifiers)
        self._sync_state_check_timer()

    def _key_event_callback(self, event: KeyboardEvent) -> None:
        """
        Callback function invoked by the 'keyboard' library for each key event.
        It normalizes the key name, updates internal state tracking pressed keys
        and active modifiers, and emits signals.

        Args:
            event: The event object from the 'keyboard' library, containing
                   attributes like 'name' and 'event_type'.
        """
        if not hasattr(event, "name") or event.name is None:
            return  # Ignore malformed events.

        normalized_key = self._normalize_key_name(event.name)
        if not normalized_key:
            return  # Ignore keys that could not be normalized.

        event_type_str = "down" if event.event_type == keyboard.KEY_DOWN else "up"

        active_modifiers = None
        with self._state_lock:
            # Update tracking of physically pressed keys.
            if event_type_str == "down":
                if normalized_key not in self._pressed_keys:
                    self._pressed_keys[normalized_key] = time.time() * 1000
            elif event_type_str == "up":
                self._pressed_keys.pop(normalized_key, None)

            # Update the set of active logical modifiers.
            modifier_base = self._get_modifier_base_name(normalized_key)
            modifiers_changed_flag = False
            if modifier_base:
                self._modifier_state_revision += 1
            if modifier_base and event_type_str == "down":
                if modifier_base not in self._active_modifiers:
                    self._active_modifiers.add(modifier_base)
                    modifiers_changed_flag = True
            elif modifier_base and event_type_str == "up":
                if modifier_base in self._active_modifiers:
                    # Keep the logical modifier while either physical side is down.
                    is_still_pressed = False
                    if modifier_base == "ctrl" and (
                        keyboard.is_pressed("left ctrl")
                        or keyboard.is_pressed("right ctrl")
                    ):
                        is_still_pressed = True
                    elif modifier_base == "shift" and (
                        keyboard.is_pressed("left shift")
                        or keyboard.is_pressed("right shift")
                    ):
                        is_still_pressed = True
                    elif modifier_base == "alt" and (
                        keyboard.is_pressed("left alt")
                        or keyboard.is_pressed("alt gr")
                        or keyboard.is_pressed("right alt")
                    ):
                        is_still_pressed = True
                    elif modifier_base == "win" and (
                        keyboard.is_pressed("left windows")
                        or keyboard.is_pressed("right windows")
                    ):
                        is_still_pressed = True

                    if not is_still_pressed:
                        self._active_modifiers.discard(modifier_base)
                        modifiers_changed_flag = True

            if modifiers_changed_flag:
                active_modifiers = self._active_modifiers.copy()

        # Preserve signal ordering for existing consumers.
        self.key_event_signal.emit(normalized_key, event_type_str)
        if active_modifiers is not None:
            self.modifiers_changed.emit(active_modifiers)
        self._state_check_sync_requested.emit()

    def start_listening(self) -> None:
        """
        Starts the global keyboard listener by hooking into system keyboard events
        using the 'keyboard' library. Also starts the timer for checking stuck key states.
        Requires appropriate permissions (e.g., administrator rights on some systems).
        """
        if not self._hooked:
            try:
                # `suppress=False` ensures events are passed to other applications as well.
                keyboard.hook(self._key_event_callback, suppress=False)
                self._hooked = True
                self._sync_state_check_timer()
                print("Keyboard listener started.")  # Console message for status.
            except Exception as e:
                # Catch common errors like permission issues.
                print(f"Error starting keyboard listener: {e}")
                print(
                    "This may be due to insufficient permissions (e.g., run as administrator) "
                    "or conflicts with other global keyboard hooks."
                )

    def stop_listening(self) -> None:
        """
        Stops the global keyboard listener, unhooks from system events,
        stops the state-checking timer, and clears internal state.
        """
        if self._hooked:
            try:
                keyboard.unhook_all()  # Remove all keyboard hooks set by this instance.
            except Exception as e:
                print(f"Error during keyboard.unhook_all(): {e}")
            self._hooked = False

        if self._state_check_timer.isActive():
            self._state_check_timer.stop()

        # Clear tracked keys and modifiers.
        with self._state_lock:
            self._pressed_keys.clear()
            self._active_modifiers.clear()
            self._modifier_state_revision += 1
            active_modifiers = self._active_modifiers.copy()
        # Emit a final modifiers_changed to reset any UI elements.
        self.modifiers_changed.emit(active_modifiers)
        print("Keyboard listener stopped.")  # Console message for status.
