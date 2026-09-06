# Shortcut Center: application discovery and unified management

## Decision

Shortcut Center is the single top-level shortcut-management entry. It combines
Catalog-backed built-in shortcuts with USER shortcuts in one application view.
The former Shortcut Library class remains as a compatibility name only; the
former USER Shortcut Manager remains available inside Center as **Advanced
Management** for profile display-name editing and built-in hide/restore work.

## Detected application versus supported application

A detected application is one valid external foreground window observed by the
existing `ForegroundMonitor -> ApplicationIdentityRuntime ->
CurrentApplicationCandidateTracker` chain. It does not need a Pack. A supported
application is a separate fact: the Catalog contains built-in APP entries for
the runtime identity. USER-only profiles stay detected-but-unsupported.

`ApplicationDescriptor` carries runtime identity, executable name/path when
available, ProductName/FileDescription when safely readable, friendly name,
optional Catalog product ID, support status, aliases, and session detection
order. Version metadata is read only for the executable already observed in the
foreground; ShortcutHUD does not scan installed applications, registries,
MSIX, Steam, or folders.

## Follow current application

Every new Center session starts in Follow Current App mode. Tracker updates and
window activation reselect the last valid external descriptor. A manual choice
turns follow off for this session only; re-enabling it immediately selects the
latest external app. No polling loop is added and no pinned choice persists.

## Unsupported applications

An unsupported current app is shown by its friendly descriptor with an explicit
“no built-in shortcut data” state and an Add Shortcut action. Its USER shortcuts
share the same table, Quick HUD selection store, recorder, validation and
atomic persistence as supported applications.

## Metadata presentation

Process identities, `legacy`, Pack IDs and resolver layers remain internal.
The Center shows only user-facing Built-in/My labels. Pack categories use stable
keys with localized labels; legacy remains Other. Recommendation is independent
metadata (`★ Recommended`) and is never appended to a description.

## Deferred boundaries

The VS Code Pack remains a 41-entry pilot, not a complete reference. This
decision does not expand Packs, add a Full Guide, build a global-registry editor
or import/download external data.
