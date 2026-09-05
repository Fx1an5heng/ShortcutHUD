# Game Guard Runtime

## Status

Accepted for the Game Guard Runtime phase.

## Context

Manual Game Mode established the presentation vocabulary, but it represented
only one session-owned boolean. Long-running use also needs two contextual
signals: a foreground window that is actually fullscreen and a user-maintained
list of applications in which passive Quick HUD presentation is unwanted.

These signals overlap. A fullscreen application can also be excluded, and the
user can enable Manual Game Mode while either contextual source remains true.
Treating the latest update as the policy state would make a weaker source erase
a stronger one; disabling Manual Game Mode could incorrectly return to
`ALLOW` while the same window is still fullscreen.

## Decision: aggregate independent sources

`SuppressionPolicy` owns three independent source decisions and exposes one
effective decision:

| Source | Decision while active | Lifetime |
| --- | --- | --- |
| Manual Game Mode | `HARD_BLOCK` | Current process session |
| Foreground fullscreen | `SOFT_BLOCK` | Current foreground context |
| Excluded foreground application | `SOFT_BLOCK` | Persistent user setting applied to current context |

The precedence is `HARD_BLOCK > SOFT_BLOCK > ALLOW`. Source updates replace
only their own value. Every presentation gate continues to ask the policy for
the effective decision; `main.py` does not duplicate source combinations.

`GameGuardRuntime` is the contextual coordinator. It converts a foreground
snapshot plus persistent settings into the fullscreen and exclusion sources,
and emits a change only when the effective policy decision changes. Manual
Game Mode is routed through the same notifier but is not persisted.

## Fullscreen definition

A foreground target is fullscreen when all of the following are true:

- the HWND exists, is visible, is not minimized, and is not DWM-cloaked;
- it is neither the desktop/shell root surface nor a window owned by the
  ShortcutHUD process;
- its visible DWM frame bounds cover the physical bounds of the monitor that
  owns the largest part of that window.

The implementation uses `DwmGetWindowAttribute` with
`DWMWA_EXTENDED_FRAME_BOUNDS`. Microsoft documents that these visible frame
bounds exclude invisible resize borders and, unlike `GetWindowRect`, are not
DPI-adjusted. A failed DWM read fails open for presentation: the window is not
classified as fullscreen.

`MonitorFromWindow(..., MONITOR_DEFAULTTONEAREST)` selects the window's own
monitor. `GetMonitorInfo` provides both `rcMonitor` and `rcWork` in virtual
screen coordinates, including negative coordinates on secondary monitors.
The fullscreen comparison is against `rcMonitor`, never merely against the
taskbar-reduced work area.

References:

- [GetWindowRect and DWM visible bounds](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect)
- [DwmGetWindowAttribute](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmgetwindowattribute)
- [DWMWA_CLOAKED](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)
- [MonitorFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-monitorfromwindow)
- [MONITORINFO](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-monitorinfo)

## Maximize is not fullscreen

A normal maximized window normally matches `rcWork`, leaving the taskbar area
uncovered. That is deliberately not fullscreen. The geometry seam also
compares how close the window is to `rcWork` when the work area differs from
the monitor. This disambiguates an auto-hidden taskbar that reserves only one
or two pixels: a window closer to `rcWork` is maximized, while a window closer
to `rcMonitor` is fullscreen.

DWM bounds can vary by a very small frame amount across Windows versions and
window frameworks. Each edge may differ from `rcMonitor` by at most two
physical pixels. The window must still be closer to `rcMonitor` than to a
distinct `rcWork`. This fixed tolerance is narrow enough to admit ordinary
borderless-frame variance without accepting a taskbar-sized gap.

No executable name, game catalog, Steam state, window title, or third-party
application identity participates in fullscreen classification.

## Scheduling and performance

Fullscreen can change while the HWND and executable remain identical. The
existing `ForegroundMonitor` therefore publishes one raw snapshot after every
existing 1000 ms polling pass, including unchanged contexts. No additional
timer or high-frequency polling loop is added.

Automatic fullscreen suppression is optional and defaults to off. At most once
per second, while the user has enabled it,
the runtime performs visibility/minimized/process checks, two DWM attribute
reads, one monitor lookup, and one monitor-info read for the foreground HWND.
When the setting is disabled, it skips fullscreen native reads. Exclusion
matching is a normalized `frozenset` lookup.

The expected transition latency is one foreground-monitor interval, roughly
one second. Existing 150 ms Quick HUD and 300 ms Win discovery delays are
unchanged.

## Exclusion identity and persistence

The settings list stores canonical resolver-facing application identities,
not display labels or raw window titles. “Add current app” uses
`CurrentApplicationCandidateTracker`, which retains the last valid external
application while the Settings window owns focus, and uses the same final
identity emitted by `ApplicationIdentityRuntime`. Paths and case normalize
through the existing `normalize_application_identity` function. Reserved
layers such as `DEFAULT`, `GLOBAL`, `WINDOWS_SHELL`, and `WPS_UNKNOWN` are not
accepted as exclusions.

`ConfigManager` persists `excluded_applications` and
`fullscreen_suppression_enabled` in `settings.json`, validates their types,
normalizes duplicates, and supplies defaults to older settings files. The
fullscreen default is off; Manual Game Mode remains absent from persistent
configuration.

Exclusions are contextual preference, not proof of a game, so they produce
`SOFT_BLOCK`. This leaves the existing policy distinction available for a
future explicitly requested Guide without implementing that surface now.

## Quick HUD convergence and input boundary

Both `SOFT_BLOCK` and `HARD_BLOCK` cancel pending Quick HUD work and hide a
visible Quick HUD immediately. When suppression returns to `ALLOW` while a
modifier from the blocked context is still held, the controller remains
disarmed until the modifier state becomes empty. The next fresh modifier hold
starts normally. This prevents a stale `Ctrl` hold from causing an unexpected
HUD pop after leaving fullscreen or removing an exclusion.

Suppression never controls `KeyboardHandler`, its global passive hook, the
active-only physical modifier reconciler, or Win release synchronization.
Input state continues to converge while presentation is blocked. Recorder and
AltGr behavior are unchanged.

## Rejected alternatives

- A last-write-wins policy cannot preserve source precedence.
- A separate fullscreen polling timer duplicates foreground work and raises
  idle cost without improving the required response target.
- Comparing only against `rcWork` classifies normal maximize as fullscreen.
- Comparing every window to the primary monitor fails on multi-monitor
  layouts and negative virtual coordinates.
- Process/game lists and application-specific branches confuse geometry with
  product identity and cannot generalize to browsers, video, or presentations.
- Pausing input hooks or reconciliation during suppression reintroduces stale
  modifier state when suppression ends.

## Known trade-offs

This is a geometry classifier, not an exclusive-fullscreen detector. A normal
application that intentionally creates a monitor-covering borderless window
is correctly treated like fullscreen because its presentation impact is the
same. Conversely, an application whose visible content is fullscreen but whose
top-level DWM frame does not cover the monitor will fail open and continue to
allow Quick HUD. The optional switch is therefore off by default; Manual Game
Mode and persistent exclusion are the reliable explicit fallbacks.
