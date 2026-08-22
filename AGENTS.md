# ShortcutHUD — AGENTS.md

## 1. Project Goal

ShortcutHUD is a lightweight Windows shortcut-discovery HUD based on the upstream project:

`ByronLeeeee/shortcut_overlay`

Current upstream baseline:

- Version: `V0.2.2`
- Commit: `474783df03c4eb676679675e549c72a1db0e38a0`
- Upstream remote: `https://github.com/ByronLeeeee/shortcut_overlay.git`
- Development branch: `shortcut-hud`

The goal is NOT to display a full virtual keyboard.

The product goal is:

> When the user holds Ctrl, Shift, Alt, Win, or a combination of modifier keys, show a small non-intrusive HUD containing useful shortcuts for the current foreground application and relevant user-defined global shortcuts.

Example:

Foreground application: VS Code

Held modifier:

`Ctrl`

HUD:

- S — Save
- F — Find
- P — Quick Open
- / — Toggle Comment
- ` — Terminal

If Shift is pressed while Ctrl remains held:

`Ctrl` → `Ctrl + Shift`

The existing HUD must update instead of creating another window.

When all relevant modifier keys are released, the HUD should disappear.

---

## 2. Global Shortcuts

ShortcutHUD must also support user-defined shortcuts that are not tied to the foreground application.

Examples may include:

- QQ screenshot
- WeChat-related shortcuts
- launching applications
- Windows utilities
- user-defined AutoHotkey shortcuts
- other global shortcuts

Global shortcuts must be stored separately from application-specific shortcuts.

The existing `DEFAULT` shortcut configuration may be reused if technically appropriate.

Application-specific shortcuts and global shortcuts may be shown together, but their origin should remain distinguishable internally.

Do not hardcode personal shortcut definitions into UI source code.

---

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

---

## 4. Existing Architecture

The current repository already contains useful components.

Relevant files:

- `main.py`
- `scripts/keyboard_handler.py`
- `scripts/foreground_monitor.py`
- `scripts/overlay_keyboard.py`
- `scripts/config_manager.py`
- `scripts/settings_dialog.py`
- `scripts/shortcut_manager_dialog.py`
- `config/shortcuts.json`
- `config/settings.json`

Current technology:

- Python 3.10+
- PySide6 / Qt
- `keyboard`
- `pywin32`
- JSON configuration

Do not assume these components must be replaced.

Inspect them first.

---

## 5. Architecture Boundaries

Keep these responsibilities separated:

### Keyboard Input

Responsible for:

- modifier key state;
- left/right modifier normalization where appropriate;
- keydown / keyup state;
- lost key-release recovery.

It must not contain shortcut database logic.

### Foreground Application Detection

Responsible for:

- identifying the foreground application;
- normalizing executable names;
- reporting application changes.

It must not contain UI rendering logic.

### Shortcut Data

Responsible for:

- application-specific shortcuts;
- global shortcuts;
- shortcut lookup;
- merging;
- deduplication;
- conflict handling.

It must not depend on the HUD implementation.

### Shortcut Matching

Responsible for mapping:

`foreground application + held modifiers`

to:

`relevant shortcut entries`

### HUD

Responsible only for presentation.

The HUD must not become the source of truth for shortcut data.

### Settings

Responsible for configurable behavior such as:

- HUD position;
- opacity;
- size;
- shortcut count;
- display delay if introduced;
- global shortcut configuration;
- startup behavior.

---

## 6. HUD Requirements

The final HUD should be substantially smaller than the upstream virtual keyboard.

Target concept:

```text
┌────────────────────────────┐
│ VS Code · Ctrl             │
│ S  Save       F  Find      │
│ P  Quick Open /  Comment   │
│ `  Terminal   B  Sidebar   │
├────────────────────────────┤
│ Global                     │
│ ... QQ Screenshot          │
└────────────────────────────┘
```

Exact dimensions should be validated experimentally.

Initial design target:

- approximately 300–420 px wide;
- compact vertical layout;
- approximately 6–10 high-value shortcuts visible;
- corner placement by default.

Required behavior:

- always on top;
- no keyboard focus;
- no activation;
- preferably mouse click-through;
- reuse one window;
- update content in place;
- low latency;
- no large animations during early phases.

Multi-monitor and DPI scaling behavior must eventually be tested.

---

## 7. Modifier Interaction

The architecture must support:

- Ctrl
- Shift
- Alt
- Win
- Ctrl + Shift
- Ctrl + Alt
- Alt + Shift
- Win combinations
- other reasonable modifier combinations

Example state transition:

```text
Ctrl down
→ Ctrl HUD

Shift down while Ctrl remains down
→ update same HUD to Ctrl+Shift

Shift up while Ctrl remains down
→ return to Ctrl HUD

Ctrl up
→ hide HUD
```

Repeated key events must not create duplicate HUD windows.

Exact show-delay behavior should be decided after testing.

The product should feel responsive while avoiding unnecessary flashing during ordinary fast shortcuts such as Ctrl+C.

---

## 8. Foreground Application Behavior

ShortcutHUD must display shortcuts for the actual foreground application.

Application switching must not leave stale shortcut data visible for an unreasonable amount of time.

The current polling design must be reviewed for responsiveness.

Do not blindly increase polling frequency without considering CPU cost and Windows APIs.

Prefer event-driven or efficient approaches if they materially improve reliability.

---

## 9. Shortcut Data Strategy

Application shortcut definitions must remain data-driven.

Initial implementation may continue using JSON.

Do not migrate configuration formats merely for architectural aesthetics.

A future PowerToys Shortcut Guide manifest importer may be considered.

Do not make Microsoft PowerToys a runtime dependency unless there is strong justification.

PowerToys data should initially be treated as a possible external source/import source, not necessarily part of the core architecture.

---

## 10. Upstream Preservation

This project began from an existing MIT-licensed upstream project.

Do not remove upstream copyright or licensing notices.

Do not rewrite the repository simply to make the code look different.

When practical:

- preserve reusable upstream components;
- isolate ShortcutHUD-specific changes;
- keep upstream remote intact;
- make changes reviewable.

---

## 11. Implementation Rules

Before modifying code:

1. Read the relevant existing files.
2. Explain how the existing implementation works.
3. Identify the smallest required change.
4. List the files that will be modified.
5. Explain important risks.
6. Only then implement.

Do not perform unrelated refactors.

Do not silently change architecture.

Do not silently replace dependencies.

Do not upgrade dependencies without explaining why.

Do not modify the global Python installation.

Use a project-local virtual environment when implementation begins.

Recommended location:

`.venv`

---

## 12. Testing Requirements

Every relevant implementation phase should eventually verify:

- Ctrl keydown triggers the correct state.
- Ctrl keyup clears the state.
- Ctrl → Ctrl+Shift updates correctly.
- Ctrl+Shift → Ctrl updates correctly.
- repeated modifier events do not create duplicate windows.
- application switching updates shortcut context.
- Ctrl+C still reaches the foreground application.
- Ctrl+V still reaches the foreground application.
- Ctrl+S still reaches the foreground application.
- Alt+Tab still works.
- Win shortcuts still work.
- the HUD does not take keyboard focus.
- the HUD does not unexpectedly activate itself.
- global shortcuts coexist with application shortcuts.
- configuration failures degrade safely.
- the application exits cleanly.

Where possible, non-UI logic should have automated tests.

Global-hook and Windows-window behavior may use reproducible manual tests when automation is impractical.

---

## 13. Agent Roles

### ChatGPT

Acts as:

- product architect;
- technical decision maker;
- cross-agent reviewer;
- acceptance reviewer.

### DeepSeek Harness

Primary role:

- independent architecture review;
- risk discovery;
- alternative proposals;
- code review.

Unless explicitly instructed otherwise, DeepSeek must NOT modify source code.

### Codex

Primary role:

- implementation;
- testing;
- debugging;
- repository changes.

Codex must not perform large architectural rewrites without approval.

No agent should assume another agent's proposal is correct.

Verify important technical claims independently.

---

## 14. Current Development Rule

The repository is currently in the architecture-review stage.

Until explicitly authorized:

DO NOT:

- modify application source code;
- install dependencies;
- create a Python environment;
- redesign the application;
- migrate configuration formats;
- replace libraries;
- implement new functionality.

Architecture inspection and planning are currently allowed.

---

## 15. Completion Reports

For implementation tasks, report:

1. What changed.
2. Why it changed.
3. Files changed.
4. Commands executed.
5. Tests executed.
6. Exact results.
7. Known limitations.
8. Risks or unresolved questions.
9. Recommended next step.

Never report success for tests that were not actually executed.