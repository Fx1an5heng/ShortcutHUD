# Input State Recovery

## The failure behind a stuck HUD

The visible symptom was simple: after a modifier had physically been released,
ShortcutHUD could continue behaving as though it were held. The persistent HUD
was only the last link in the failure. The actual stale state began in the
keyboard observer, kept the controller's canonical modifier non-empty, and
therefore left pending or visible presentation work valid from the
controller's point of view.

This distinction mattered. Hiding the HUD on an application switch, adding an
exception for the software that exposed the problem, or changing hook
suppression would have treated a symptom while weakening normal keyboard
behavior. The invariant needed to be stated at the input boundary: once the
physical modifiers are up, the internal logical state must eventually agree.

## What the investigation found

`KeyboardHandler` owns two related collections:

- `_pressed_keys`, used for normalized key-down/key-up tracking;
- `_active_modifiers`, the logical `ctrl` / `alt` / `shift` / `win` set emitted
  to consumers.

The handler already ran a 50 ms timer and described it as stuck-key recovery.
That initially made the failure surprising. Reading the installed `keyboard`
package showed that `keyboard.is_pressed()` checks its `_pressed_events` table,
which is itself populated and cleared by the same hook event stream. A missed
key-up can therefore make the recovery check stale in exactly the same way as
ShortcutHUD's own collections.

Left/right collapsing exposed a second hole. Both Control sides normalize to
`Ctrl`. Releasing one side removes the single `_pressed_keys["Ctrl"]` entry,
while `_active_modifiers` correctly remains `ctrl` if the other side is down.
If the second side's up event is then missed, the old recovery loop has no
`Ctrl` entry left to inspect at all.

Controller behavior was already correct for a trustworthy empty modifier
state. `on_modifiers_changed(set())` stops the single-shot timer, hides the HUD,
and resets Win presentation flags. The controller therefore did not need a new
physical-key dependency.

Win required one extra audit. Besides controller flags, `WinDiscoveryProxy`
tracks physical Win sides and one active discovery side. Its explicit release
callback is an important fast path, but it cannot be the only recovery path for
the very failure class in which a hook misses key-up. Leaving the proxy state
behind could contaminate a later hold, particularly on the opposite Win side.

## The resulting design

The new physical adapter reads the high bit of `GetAsyncKeyState` for left and
right Control, Alt, Shift, and Win. A fake callable can replace the native API
in tests, keeping the comparison logic deterministic.

The reconciler computes a release-only correction. It intersects the internal
logical set with the physical logical set, so `Ctrl+Shift` can become `Ctrl`
without clearing a modifier that is still held. It never adds a physical key
the hook did not observe. A failed native read returns no correction rather
than treating every key as released.

`KeyboardHandler` applies the correction under its state lock, removes the
matching normalized entries, emits logical release events, and emits exactly
one corrected modifier set. A revision guard rejects a sampled result when a
newer modifier hook event arrived during the native read. This is important for
the case where a stale logical `ctrl` is sampled as up just as the user begins
a fresh Control hold: the new event must win.

The same release event asks `WinDiscoveryProxy` to prune stale native Win state.
The proxy method is narrow and idempotent. It does not arm a session, stop the
hook, or inject cleanup keys, and it leaves a side alone while Windows still
reports that side down.

## Timer trade-off

The watchdog now runs at 100 ms instead of keeping the old 50 ms timer alive
permanently. It starts only while the handler has an active logical modifier;
a terminal key alone does not start it, and the timer stops at idle. The
legacy non-modifier check still gets an opportunity to run while a modifier is
active without owning a permanent polling lifecycle.

100 ms was selected against the existing presentation timings rather than as
an arbitrary background-polling rate. It is below the 150 ms ordinary HUD
threshold and well below the 300 ms Win threshold, which gives an immediately
missed release a chance to cancel pending presentation before it appears. It
also halves the active sampling frequency compared with the previous timer and
removes all normal idle wakeups. One active pass makes at most eight native key
state reads.

The timer lifecycle has to change on the Qt thread even though global hook
callbacks arrive on a worker thread. An internal queued signal now requests
start/stop synchronization rather than manipulating `QTimer` directly from the
hook callback.

## AltGr and input ownership

The physical layer deliberately avoids semantic interpretation. Right Alt is
read as right Alt; if Windows also reports Control during AltGr, those are only
physical facts. Because reconciliation is removal-only, it cannot synthesize a
`Ctrl+Alt` candidate, change Recorder's explicit AltGr rejection, or create a
new HUD interaction.

The global hook remains `suppress=False`. No input is swallowed or rewritten,
and no foreground application name participates in recovery. Manual Game Mode
continues to suppress presentation only; the input state still converges while
`HARD_BLOCK` is active.

## Verification

The automated coverage added in this phase exercises:

- normal Control down/up and passive hook installation;
- all eight left/right modifier virtual keys and high-bit-only interpretation;
- stale `Ctrl` to idle and stale `Ctrl+Shift` to physically held `Ctrl`;
- physical-read failure and hook/read race behavior that preserve newer state;
- pending timer cancellation and visible HUD hiding through the normal signal
  chain;
- pending and active Win discovery cleanup, including the proxy's native
  session;
- preservation of the opposite Win side;
- recovery during `HARD_BLOCK` and a fresh Control hold after it is disabled;
- observable Ctrl+C, Ctrl+V, Ctrl+S, Alt+Tab, and Win+R event sequences;
- the existing Recorder AltGr and logical-symbol tests.

The pre-change suite passed 277 tests. After this phase, the full suite passes
299 tests. `git diff --check` also passes.

## Remaining manual confidence checks

Automation can deterministically model a missed hook event, but a release
swallowed by real Windows UI or a third-party overlay still needs a short smoke
pass. The useful checks are repeated quick release before the HUD threshold,
release after the HUD is visible, partial `Ctrl+Shift` release, both Win sides,
AltGr input, and Game Mode on/off recovery. The foreground application should
continue receiving Ctrl+C/V/S, Alt+Tab, and Win shortcuts throughout.

## Scope held

This phase does not add fullscreen detection, application exclusions,
automatic game detection, catalog or Guide surfaces, delay tuning, PowerToys
integration, macOS behavior, or a new input mode. It repairs one Windows input
state invariant while preserving the current presentation and data layers.
