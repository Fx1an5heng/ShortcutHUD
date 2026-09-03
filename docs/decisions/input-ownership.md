# Input Ownership

## Context

ShortcutHUD discovers and teaches shortcuts; it does not remap keys, execute
macros, or replace an application's input handling. Passive ShortcutHUD
surfaces must never take ownership of normal application input.

The following states describe product ownership boundaries. They are not a
requirement for one large runtime state-machine class.

## States and ownership

### IDLE

No ShortcutHUD presentation owns input. The global keyboard observer may track
modifier state, but it must not suppress or rewrite events.

### QUICK_HUD

Quick HUD is passive. It observes modifier state, does not activate or take
focus, and does not swallow keys. The foreground application and Windows keep
full ownership of keyboard input.

### GUIDE (future)

Guide is opened explicitly by the user. Only after its own window is active may
it process navigation intended for that window. Opening Guide must not change
the meaning of shortcuts delivered to another foreground application.

### KEYPATH (future, inside Guide)

KeyPath is hierarchical navigation owned by an already-active Guide. It is not
a new global keyboard mode and must not install a second hidden hook.

### RECORDING

Recorder starts only after an explicit click in the shortcut editor. It handles
local Qt key events belonging to that settings dialog and stops when recording
finishes, is cancelled, or the dialog loses focus. It remains available while
Manual Game Mode is on.

### SUPPRESSED

Automatic HUD and passive learning presentations are not allowed to appear.
Keyboard observation may continue so release recovery remains correct, but
suppression must not consume, rewrite, or synthesize user input.

## Decision

Presentation suppression belongs above keyboard-state collection. Keyboard
handlers report state; presentation policy decides whether ShortcutHUD may
show. This preserves the invariant that passive ShortcutHUD surfaces never
take normal input away from the foreground application.
