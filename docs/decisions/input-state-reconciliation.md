# Input State Reconciliation

## Status

Accepted for the Input State Recovery phase.

## Context

ShortcutHUD derives its logical modifier state from global hook events. A
normal key-down/key-up pair keeps that state accurate, but Windows system UI,
another overlay, an input method, or another hook can prevent one observer from
seeing a key-up. The user may then have physically released every modifier
while ShortcutHUD still believes that `Ctrl`, `Alt`, `Shift`, or `Win` is held.

This is a state-consistency problem, not an application-compatibility problem.
An application-specific exception would only hide one trigger and leave the
same failure available through every other system surface or third-party hook.

The previous stuck-key check did not provide an independent truth source. Both
`KeyboardHandler._pressed_keys` and `keyboard.is_pressed()` are derived from
the `keyboard` package's hook event table. If that hook misses a key-up, both
views can remain stale together. The handler also collapses left and right
modifier events into one logical key name. After one side is released,
`_pressed_keys` may no longer contain that logical name even though the logical
modifier remains active for the other side, leaving nothing for the old loop
to inspect if the second release is missed.

## State model

There are three related states with distinct ownership:

| State | Owner | Role |
| --- | --- | --- |
| Physical left/right modifier state | Windows | Current physical truth sampled independently of the hook |
| Active logical modifier set | `KeyboardHandler` | Single source of truth for observed ShortcutHUD input |
| Canonical modifier and HUD work | `ShortcutHudController` | A downstream projection used for resolution, timers, and presentation |

The controller must not query Windows or repair keyboard state. A correction
is applied to `KeyboardHandler` and propagated through its existing
`key_event_signal` and `modifiers_changed` signals. The controller then follows
its normal path to cancel a pending timer, hide a visible HUD, and reset Win
discovery flags.

## Decision

Add a testable `PhysicalModifierReconciler` behind `KeyboardHandler`.

The production reader samples `GetAsyncKeyState` for both sides of every
modifier:

- left/right Control;
- left/right Alt (`VK_LMENU` / `VK_RMENU`);
- left/right Shift;
- left/right Windows.

Only bit `0x8000`, the high-order "currently down" bit, is read. The low-order
"pressed since the previous query" bit is deliberately ignored because it is
not current physical state and Microsoft documents it as unreliable. See
[GetAsyncKeyState](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getasynckeystate).

Reconciliation is release-only:

```text
corrected logical state = internal logical state ∩ physical logical state
```

It can remove a stale modifier but cannot invent a key-down that the hook did
not observe. If any physical-state read fails, the reconciler keeps the current
internal state and retries later. A revision counter also prevents a snapshot
from overwriting a newer hook event that arrived while the physical read was in
progress.

This preserves input ownership: the hook still decides when a ShortcutHUD
interaction starts, and reconciliation only lets an incorrectly extended hold
end.

## Scheduling and performance

The reconciliation watchdog runs every 100 ms only while `KeyboardHandler`
owns a non-empty logical modifier state. A terminal key by itself does not
start it, and it stops as soon as the modifier set becomes empty. Normal
application idle therefore adds no timer wakeups and no `GetAsyncKeyState`
calls. The legacy non-modifier stuck-key check still runs opportunistically
during those active modifier windows.

The 100 ms interval is intentionally shorter than the existing 150 ms ordinary
HUD delay and 300 ms Win-only delay. A release missed immediately after
key-down can normally be corrected before the first HUD show; a release missed
just after a sample remains stale for at most roughly one further interval.
During an active hold, one pass reads at most eight inexpensive physical key
states, or at most 80 native calls per second. This replaces the previous
permanent 50 ms timer, which woke during idle but still consulted hook-derived
state.

The 150 ms and 300 ms presentation delays are unchanged.

## Win state

Win discovery has additional native state in `WinDiscoveryProxy`. The proxy's
existing physical-release callback remains the fast path. General
reconciliation covers ordinary Win holds, pre-activation releases, and missed
callback cases while preserving the other physical Win side.

When reconciliation emits the normal logical `Win` up event, application
orchestration asks the proxy to discard only physical Win sides that are no
longer down. This cleanup is idempotent, injects no input, and preserves an
active side still reported as physically held. The controller separately
receives `modifiers_changed` and clears pending or active discovery UI state.

## AltGr boundary

AltGr remains fail-closed. The physical reader observes right Alt and Control
as the ordinary physical keys Windows reports, but reconciliation never
creates `Ctrl+Alt`, never turns right Alt into a new semantic modifier, and
never changes Recorder behavior. It can only retain or remove logical tokens
already produced by the existing input adapter.

## Suppression boundary

Manual Game Mode remains presentation-only. `HARD_BLOCK` does not stop the
keyboard observer or the reconciliation timer. Recovered state still reaches
the controller, which remains unable to show the HUD while blocked. After Game
Mode is disabled, the next observed modifier down starts normally without a
process restart.

## Rejected alternatives

- Enabling hook suppression would violate ShortcutHUD's input-ownership rule.
- Clearing modifiers on every foreground change would incorrectly cancel a
  physically held chord during a legitimate application switch.
- Adding executable-specific workarounds would not solve the shared state
  model.
- Querying physical state in the controller would create a second input source
  and could leave handler and presentation state inconsistent.
- Inferring missed key-down events from polling could show a HUD without an
  observed user interaction and would increase AltGr ambiguity.
- Permanent high-frequency polling would add idle cost without improving the
  required convergence guarantee.

## Consequences

Missed modifier key-up events now converge through the same downstream update
path as observed releases. Recovery is bounded by an active-only watchdog, all
left/right sides are respected, and read failures preserve state rather than
causing false releases. The design remains Windows-specific at the physical
adapter boundary and does not add any application knowledge.
