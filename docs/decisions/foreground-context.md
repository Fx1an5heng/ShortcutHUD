# Foreground context: actual state and external fallback

## Decision

ShortcutHUD keeps two related but non-interchangeable values in
`CurrentApplicationCandidateTracker`:

- **Actual Foreground Context** is the latest context Windows reported. It can
  be an external application, `Windows Desktop`, ShortcutHUD itself, or absent
  when the shell surface cannot be safely classified.
- **Last External Application** is the latest ordinary external application.
  It is retained only when ShortcutHUD takes focus, so Settings and its child
  Shortcut Center can still offer “add the app the user came from”.

Shortcut Center follows actual external or desktop contexts. When its own
window is foreground, it falls back to the last external application. It must
never present that fallback as the actual foreground context.

## Desktop and shell classification

Explorer is not a single semantic context. `Progman` and `WorkerW` are
classified as `SHELL_DESKTOP` and receive a first-class `Windows Desktop`
descriptor. File Explorer window classes remain `EXPLORER.EXE`; taskbar, Start
and unfamiliar Explorer-owned surfaces remain the non-customizable
`WINDOWS_SHELL` context. Desktop is global-only and cannot receive a USER
application profile in this phase.

## Foreground delivery

The existing `WinEventHook` listens for `EVENT_SYSTEM_FOREGROUND` as the
low-latency primary trigger. Its native callback only queues a Qt signal; the
main-thread slot calls the existing `ForegroundMonitor`, whose normal signals
continue through `ApplicationIdentityRuntime` and the candidate tracker. No
second resolver or UI work is performed in the native callback.

This follows the Win32 `SetWinEventHook` contract: out-of-context delivery
requires a message loop and may run on the registration thread. Qt's queued
connections place the receiver work back on the receiver's event loop. The
existing 1000 ms `ForegroundMonitor` timer remains a reconciliation fallback
for a missed or unavailable event hook, rather than becoming high-frequency
polling.

References: [SetWinEventHook (Microsoft Learn)](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwineventhook),
[Qt thread synchronization](https://doc.qt.io/qt-6/threads-synchronizing.html).

## Settings navigation

Settings alone uses `WindowStaysOnTopHint`; Quick HUD flags are untouched.
Opening Shortcut Center from Settings hides the same Settings instance. The
modal Center is then run, and Settings is restored in a `finally` block so its
geometry and unsaved UI state remain intact. A live Center instance is raised
instead of creating a duplicate.

## Consequences and limits

This improves prompt external application changes without application-specific
rules or keyboard-triggered refreshes. Shell-class interpretation is
conservative: unfamiliar Explorer surfaces do not masquerade as the desktop.
The event hook still skips this process, so self context continues to be
reconciled by the established monitor path; this preserves the existing
non-invasive hook behavior.
