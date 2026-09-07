# Foreground context correction after Windows smoke testing

## The symptom was a state-model bug

The smoke report exposed two different failures with one root cause. Returning
from VS Code to the desktop left Center showing VS Code, and a newly foreground
application could wait for the periodic monitor (or a later interaction) before
appearing. The tracker had one “latest external” descriptor which was useful
for Settings, but Center also treated it as the current foreground application.

That shortcut was wrong on the desktop. A desktop is a real context, while
ShortcutHUD's own Settings window is the only case that should deliberately use
the last external app as a UI fallback.

## The correction

`ApplicationDescriptor` now expresses a context kind. Explorer's `Progman`
and `WorkerW` top-level windows become the `SHELL_DESKTOP` descriptor, rendered
as `Windows Desktop` / `Windows 桌面`; File Explorer, taskbar and other Explorer
surfaces retain their separate classifications. The candidate tracker now keeps
actual context and last external descriptor separately. Desktop changes actual
context only, so it cannot erase the useful external fallback or enter recent
application history.

The pre-existing `SetWinEventHook` bridge was already the right integration
point. It is now the immediate trigger for the existing monitor and identity
pipeline, while the existing 1000 ms monitor remains recovery polling. The
native callback stays small and the queued Qt bridge prevents it from touching
widgets or tracker state directly.

## Product polish without scope expansion

Settings is explicitly topmost, but no Quick HUD flags changed. Settings hides
before opening Center and restores itself in a `finally` block after Center
closes. The live Center is reused if asked to open again. This fixes overlapping
product windows without adding another dialog owner or a separate navigation
framework.

## Verification focus

New tests cover desktop descriptor/classification, actual versus last-external
semantics, duplicate foreground-context suppression, the queued foreground
event path, Center follow/manual pin behavior, Settings topmost flags, and
Settings-to-Center restoration. Existing resolver and input/HUD suites remain
the regression boundary; Windows smoke remains necessary for Win+D, Alt+Tab,
and shell-window variability.
