# Suppression Policy

## Decision

All ShortcutHUD presentation surfaces use one small policy vocabulary:

- `ALLOW`: passive and user-initiated presentations are allowed.
- `SOFT_BLOCK`: passive presentations are blocked, while a future explicitly
  requested Guide may still open.
- `HARD_BLOCK`: every ShortcutHUD overlay or passive presentation is blocked.

Tray, Settings, and About are control surfaces rather than shortcut
presentations. They remain available under every decision so the user can
inspect the application and turn Manual Game Mode off. Recorder remains
available because it is an explicitly entered, settings-local input mode.

## Intent matrix

| Decision | Passive Quick HUD / Learning | User-initiated Guide |
| --- | --- | --- |
| `ALLOW` | Allow | Allow |
| `SOFT_BLOCK` | Block | Allow |
| `HARD_BLOCK` | Block | Block |

## Sources

- Manual Game Mode produces `HARD_BLOCK`.
- A future user-excluded game or application will produce `HARD_BLOCK`.
- Future automatic fullscreen detection should produce `SOFT_BLOCK`.

Fullscreen alone is not evidence of a game. It may be an IDE, browser, PDF,
video, or presentation. Treating it as `HARD_BLOCK` would incorrectly override
an explicit user request to open Guide.

## Runtime boundary

The policy is pure logic and does not own hooks, timers, foreground polling, or
widgets. Presentation controllers query it before scheduling or showing work.
When the decision becomes `HARD_BLOCK`, the owning controller cancels pending
show work and hides an already-visible surface immediately.

Manual Game Mode is session-only in Phase G0. It defaults to off at every
process start and is intentionally absent from settings persistence.
