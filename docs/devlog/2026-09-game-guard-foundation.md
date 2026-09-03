# Game Guard Foundation

## Background

A HUD that appears during a game or another high-focus activity is more than a
minor visual annoyance. It can cover important content and make the user doubt
whether ShortcutHUD is interfering with input. Game Guard establishes a clear
way to suppress presentation without changing keyboard behavior.

## Goal

Phase G0 adds a maintainable project-record structure, a shared suppression
vocabulary, and a session-only Manual Game Mode. It does not add automatic game
or fullscreen detection, application lists, Full Guide, KeyPath, Learning Mode,
or macOS support.

## Existing Architecture

Before this change, `KeyboardHandler.modifiers_changed` delivered the current
logical modifier set to `ShortcutHudController`. The controller canonicalized
the set, resolved shortcuts for the foreground application, and either updated
an already-visible HUD or started its single-shot show timer. The timer used
150 ms for ordinary modifiers and 300 ms for Win-only discovery. Its timeout
re-resolved current data before rendering and calling `show_hud()`.

The controller already owned all Quick HUD scheduling and visibility, making it
the narrowest reliable boundary for presentation suppression. Recorder was
separate: it installed local Qt event filters only inside the shortcut editor
after an explicit Record action.

## Design

The suppression vocabulary is:

- `ALLOW` for normal operation;
- `SOFT_BLOCK` for future contextual suppression that blocks passive hints but
  preserves explicitly invoked Guide access;
- `HARD_BLOCK` for an explicit user request to block every ShortcutHUD
  presentation surface.

Manual Game Mode maps to `HARD_BLOCK`. The policy stays independent of Qt,
keyboard hooks, foreground monitoring, and persistence.

## Implementation

- Added a pure suppression policy and intent evaluator.
- Injected the shared policy into `ShortcutHudController`.
- Checked the policy before timer scheduling and before a pending HUD can show.
- Applied policy changes immediately so pending timers stop and visible HUDs
  hide.
- Added a checkable Game Mode action to the tray menu.
- Kept Game Mode in process memory only; it is not written to settings.
- Kept Settings, About, and settings-local Recorder available.
- Blocked the legacy overlay presentation while `HARD_BLOCK` is active.

No keyboard-hook, Win proxy, Recorder, resolver, or foreground-monitor code was
changed.

## Problems Encountered

No major implementation issue was encountered. The initial `git fetch origin`
verification was attempted twice but GitHub connectivity was reset and then
timed out. The local `origin/main`, release tag, and working HEAD all matched
commit `2ce215c` with a zero ahead/behind count, so that recent remote-tracking
state was used as the trusted base. A final pre-commit fetch succeeded and
confirmed that `origin/main` was still the same commit.

## Testing

The pre-change suite passed 265 tests. Targeted suppression and controller tests
cover the policy decisions, pending-timer cancellation, immediate hiding, and
restoration without restarting. Tray wiring tests cover checkable session state
and policy propagation.

After the change, the full suite passed 277 tests. The manual smoke status is
recorded in the Phase G0 completion report.

## Trade-offs

- Automatic game detection is deferred because reliable classification needs a
  separate evidence and policy phase.
- Manual Game Mode is session-only so a forgotten setting cannot silently leave
  ShortcutHUD disabled after restart.
- The keyboard hook continues running so modifier release recovery and normal
  shortcut delivery are unchanged.
- Persistent Game Mode is deferred until the product can make disabled state
  obvious and recoverable.

The current 150 ms Quick HUD delay is deliberately unchanged. Interaction
Polish should compare 60, 80, 100, 120, and 150 ms and may later expose Fast,
Balanced, Relaxed, and Custom choices.

## Result

Manual Game Mode now establishes a reusable `HARD_BLOCK` presentation decision.
Turning it on cancels pending Quick HUD work and hides visible HUD surfaces;
turning it off restores eligibility immediately without restarting hooks or the
application.

## Commits

- `f00c9b5` — `feat: add manual game mode guard`
- `docs: add ShortcutHUD engineering decision records` — the documentation
  commit that contains and finalizes this record.
