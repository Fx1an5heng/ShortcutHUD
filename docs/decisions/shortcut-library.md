# Shortcut Library v1

## Status

Accepted for the Shortcut Library v1 phase.

## Catalog is not a HUD preference list

The Catalog describes what shortcuts exist and where they came from. Quick HUD
selection describes what one user wants to see for one application. Combining
those concerns would make a Pack update overwrite preference, or make a
preference write modify bundled data. The Library is therefore a selection
manager, not a Full Guide and not a second shortcut database.

## Selection contract

The selection document distinguishes two states exactly:

- no application key: use Catalog `recommended` defaults;
- application key with `[]`: the user explicitly selected no application
  entries.

“Restore Recommended” deletes the application key. “Clear All” writes the
empty array. They deliberately cannot share an implementation.

Selection applies to `USER_APP`, `APP`, and `DEFAULT` candidates only. Shared
`GLOBAL` entries continue through the existing resolver layering, so clearing
an application's rows never silently redefines global shortcuts.

## Stable-ID migration

Formal Pack entries use durable author-owned IDs such as `vscode.quick-open`.
An entry may declare `id_aliases`, currently used to map known legacy adapter
IDs. When a persisted selection contains one of those aliases, the selection
store resolves it to the formal entry ID in memory. Unknown/stale IDs are
ignored safely and retained on disk rather than being guessed or destroyed.

No migration uses localized description text, command position, or search
results. Those values are presentation data and are not stable identity.

## Library v1 boundary

The dialog reads the initialized in-memory Catalog, combines builtin and
existing USER entries for the chosen application, and persists changes through
the atomic `QuickHudSelectionStore`. It offers an application selector,
case-insensitive search, a plain checkbox table, selected-count feedback,
Restore Recommended, and Clear All.

It does not become a Full Guide: it has no temporary fullscreen reference,
command runner, navigation system, or separate shortcut editor. The current
modifier-triggered HUD continues to filter the selected rows at hold time.

## VS Code pilot strategy

The first formal Pack covers 41 representative Windows shortcuts from the
official VS Code default keyboard-shortcut reference: General, Basic editing,
Navigation, Search, Display, Editor, File management, and Integrated terminal.
It intentionally stops well short of a complete command corpus. Each entry
has English and Simplified Chinese content, category, aliases, source metadata,
stable ID, deterministic rank, and a conservative recommended subset.

When a formal Pack covers an application identity, its app entries replace the
legacy adapter's builtin app rows for that identity. This prevents duplicated
CODE.EXE rows and makes the Pack's recommendation policy meaningful. Other
applications remain on the legacy adapter unchanged.
