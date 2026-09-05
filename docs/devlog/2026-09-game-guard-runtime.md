# Game Guard Runtime

## The gap after Manual Game Mode

Manual Game Mode proved that ShortcutHUD could stop presenting without
stopping input observation, but it left the user responsible for every context
transition. A browser entering F11, a borderless player, or a deliberately
excluded remote-desktop application should not require repeated tray toggles.

The first design pressure was not fullscreen geometry. It was state
composition. Manual Game Mode already meant `HARD_BLOCK`; fullscreen and
exclusion were both intended to mean `SOFT_BLOCK`. If a single mutable policy
field represented all three, update order would become product behavior. The
classic failure sequence was fullscreen on, Manual Game Mode on, Manual Game
Mode off: a last-write implementation would return `ALLOW` even though the
fullscreen reason had never disappeared.

## Runtime shape

The implementation was divided into four narrow parts:

1. `SuppressionPolicy` stores independent manual, fullscreen, and exclusion
   sources and calculates the strongest effective decision.
2. `WindowsFullscreenDetector` translates one HWND into an eligibility and
   geometry snapshot. Its final comparison is a pure function.
3. `GameGuardRuntime` evaluates the current context, updates both contextual
   policy sources together, and notifies presentation only when the effective
   decision changes.
4. Settings owns user editing and persistence, while the existing application
   identity pipeline supplies canonical IDs.

This kept Windows geometry out of the policy, policy combinations out of
`main.py`, storage out of the detector, and application names out of input
handling.

## Reusing the foreground cadence

`ForegroundMonitor` already wakes every 1000 ms, but its original signals only
described transitions. That is enough for shortcut lookup and wrong for
fullscreen: the same Chrome HWND can move from maximized to F11 and back while
its executable never changes.

Rather than introduce a watchdog, the monitor now publishes a second snapshot
after every existing check. The transition signal keeps its old semantics for
application identity. The polling signal feeds only runtime context. This
gives fullscreen a roughly one-second convergence target with no new timer and
no increase in the existing polling frequency.

## Windows API choices and the maximize trap

The initial geometry model was “visible frame approximately equals monitor.”
`DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` was selected over raw
`GetWindowRect`: it excludes invisible resize borders and returns bounds not
adjusted by DPI virtualization. `MonitorFromWindow` chooses the monitor with
the largest intersection, and `GetMonitorInfo.rcMonitor` supplies that
monitor's full virtual-screen rectangle. This naturally supports secondary
monitors with negative or offset coordinates.

The important negative case is a maximized window. Its boundary follows
`rcWork`, not the full monitor. A two-pixel DWM tolerance initially exposed a
subtler version of the same problem: an auto-hidden taskbar may reserve only a
thin strip, so a maximized work-area window can also be within the monitor
tolerance. The final comparison measures distance to both rectangles. A
window closer to a distinct `rcWork` is rejected; a window closer to
`rcMonitor` can pass. This retains the narrow tolerance without converting it
into an auto-hide false positive.

Eligibility is checked before geometry. Invalid HWNDs, hidden, minimized, or
DWM-cloaked windows, desktop/shell root surfaces, and ShortcutHUD's own process
fail open. There is no executable allowlist or game detector. Explorer's
ordinary windows simply do not cover the physical monitor and therefore do not
pass.

## Exclusion editing without a second identity system

Opening Settings changes the foreground window to ShortcutHUD, which makes a
naive “add foreground exe” button add the wrong process. The existing
`CurrentApplicationCandidateTracker` already solves this for the shortcut
editor: it retains the latest valid external application and ignores the
project's own PID and reserved identities. The Game Guard button uses that same
provider.

Stored exclusions use the resolver-facing IDs already published by
`ApplicationIdentityRuntime`. The settings normalizer strips paths, normalizes
case, rejects reserved identities, and removes duplicates while preserving
list order. This also keeps WPS logical application identity behavior aligned
with shortcut resolution instead of falling back to raw window titles.

Older settings files receive two defaults on load: automatic fullscreen
suppression disabled, and an empty exclusion list. Invalid types are replaced
with safe defaults and the normalized list is persisted. Manual Game Mode is
still session-only.

## The stale-hold presentation edge

Stopping suppression could previously call `refresh_current_state()` while
the controller still held `Ctrl`, immediately scheduling a HUD for an
interaction that began in a blocked context. It was technically consistent
and visually surprising.

The controller now latches a small presentation-only rearm flag whenever a
non-empty modifier exists under a blocking policy. Returning to `ALLOW` keeps
pending work canceled until modifiers become empty. A subsequent fresh hold
uses the unchanged 150 ms or 300 ms path. This does not alter the input source
of truth: `KeyboardHandler` continues updating and recovering modifier state
throughout SOFT and HARD blocks.

## Verification

The added coverage exercises all source combinations and precedence; same-HWND
fullscreen entry/exit; monitor, work-area, two-pixel tolerance, auto-hidden
taskbar, hidden/minimized/cloaked, shell, own-process, and second-monitor
geometry; disabling fullscreen reads; exclusion add, remove, unrelated-app
behavior, normalization, and reload persistence; pending and visible HUD
convergence; fresh-modifier rearm; and input reconciliation during
`SOFT_BLOCK`.

The complete suite passes 331 tests, including the existing AltGr recorder,
Ctrl+C/V/S, Alt+Tab, Win discovery/release, input state reconciliation,
application identity, and Manual Game Mode coverage. `git diff --check` also
passes.

## Trade-offs kept explicit

- Detection is optional and defaults off. When enabled, latency is bounded by
  the existing one-second polling interval, not a new high-frequency watcher.
- A monitor-covering borderless productivity window is intentionally treated
  the same as fullscreen; the user-facing concern is passive overlay conflict,
  not whether the process is a game.
- If DWM geometry cannot be read, automatic suppression fails open. The user
  can still choose exclusion or Manual Game Mode.
- No attempt is made to infer games, detect exclusive DirectX mode, inspect
  Steam, tune HUD delays, or build a future Guide surface.
