# ShortcutHUD — AGENTS.md

## 1. Project Goal

ShortcutHUD is a lightweight Windows shortcut-discovery HUD based on the upstream project:

`ByronLeeeee/shortcut_overlay` (MIT License)

Upstream baseline: `V0.2.2`, commit `474783df03c4eb676679675e549c72a1db0e38a0`.

The goal is NOT to display a full virtual keyboard.

> When the user holds Ctrl, Shift, Alt, Win, or a combination of modifier keys, show a small non-intrusive HUD containing useful shortcuts for the current foreground application and relevant user-defined global shortcuts.

Held modifier example: `Ctrl` → HUD shows S — Save, F — Find, P — Quick Open, / — Toggle Comment, ` — Terminal. When Shift is pressed while Ctrl remains held the existing HUD updates in place (Ctrl → Ctrl+Shift). When all modifiers are released the HUD disappears.

## 2. Global Shortcuts

ShortcutHUD supports user-defined shortcuts that are not tied to the foreground application (screenshot tools, chat apps, launching programs, Windows utilities, AutoHotkey shortcuts, and others).

Global shortcuts must be stored separately from application-specific shortcuts. Application shortcuts and global shortcuts may be shown together, but their origin remains distinguishable internally. Do not hardcode personal shortcut definitions into UI source code.

## 3. Core Product Principles

Priority order:

1. Never interfere with normal keyboard input.
2. Never swallow or alter existing shortcuts.
3. Never steal focus from the foreground application.
4. Modifier detection must feel responsive.
5. The HUD must remain visually small.
6. Prefer mature existing code over unnecessary rewrites.
7. Prefer configuration-driven behavior over hardcoded shortcut tables.
8. Keep application shortcut data separate from UI code.
9. Keep global shortcut data separate from application-specific shortcut data.
10. Make the smallest coherent change needed for each development phase.

Visual polish is secondary to reliability.

## 4. Architecture Boundaries

Keep these responsibilities separated:

### Keyboard Input

Responsible for: modifier key state; left/right modifier normalization; keydown/keyup state; lost key-release recovery. It must not contain shortcut database logic.

### Foreground Application Detection

Responsible for: identifying the foreground application; normalizing executable names; reporting application changes. It must not contain UI rendering logic.

### Shortcut Data

Responsible for: application-specific shortcuts; global shortcuts; shortcut lookup; merging; deduplication; conflict handling. It must not depend on the HUD implementation.

### Shortcut Matching

Responsible for mapping `foreground application + held modifiers` to `relevant shortcut entries`.

### HUD

Responsible only for presentation. The HUD must not become the source of truth for shortcut data.

### Settings

Responsible for configurable behavior such as HUD position, opacity, size, shortcut count, display delay, global shortcut configuration, and startup behavior.

## 5. HUD Requirements

- Always on top, no keyboard focus, no activation, preferably mouse click-through.
- Reuse one window; update content in place; low latency.
- No large animations in early phases.
- Multi-monitor and DPI scaling behavior must eventually be tested.

## 6. Shortcut Data Strategy

Application shortcut definitions remain data-driven (JSON). A future PowerToys Shortcut Guide manifest importer may be considered. Do not make Microsoft PowerToys a runtime dependency unless there is strong justification.

## 7. Upstream Preservation

This project began from an existing MIT-licensed upstream project. Do not remove upstream copyright or licensing notices. Do not rewrite the repository simply to make the code look different. When practical: preserve reusable upstream components, isolate ShortcutHUD-specific changes, keep the upstream remote intact, and make changes reviewable.

## 8. Implementation Rules

Before modifying code:

1. Read the relevant existing files.
2. Explain how the existing implementation works.
3. Identify the smallest required change.
4. List the files that will be modified.
5. Explain important risks.
6. Only then implement.

Do not perform unrelated refactors. Do not silently change architecture. Do not silently replace dependencies. Do not upgrade dependencies without explaining why. Do not modify the global Python installation. Use a project-local virtual environment (`.venv`).

## 9. Testing Requirements

Every relevant implementation phase should verify:

- Modifier keydown/keyup and combination transitions behave correctly.
- Repeated modifier events do not create duplicate HUD windows.
- Application switching updates shortcut context.
- Ctrl+C / Ctrl+V / Ctrl+S still reach the foreground application.
- Alt+Tab and Win shortcuts still work.
- The HUD does not take keyboard focus or activate itself.
- Global shortcuts coexist with application shortcuts.
- Configuration failures degrade safely.
- The application exits cleanly.

Non-UI logic should have automated tests where possible. Global-hook and Windows-window behavior may use reproducible manual tests when automation is impractical.

## 10. Local Development Instructions

If `AGENTS.local.md` exists in the repository root, it may contain local development instructions and must never be committed.
