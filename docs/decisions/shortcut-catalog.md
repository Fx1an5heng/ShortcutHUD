# Shortcut Catalog Foundation

## Status

Accepted for the Catalog Foundation phase.

## Context

`config/shortcuts.json` is a deliberately small, legacy-friendly mapping:
application identity, held modifier, terminal key, and a display description.
It works for the current Quick HUD but has no stable entry identity, source
metadata, category, rank, visibility target, aliases, or representation for a
future sequence. Making the HUD window own those facts would turn a
presentation component into the shortcut database.

The project needs a data model that can grow into a catalog and a guide while
leaving today's user shortcuts, editor, and HUD output intact.

## Decision

Introduce a pure Catalog domain layer between stored data and shortcut
resolution. `CatalogEntry` has a stable ID; a structured trigger (`combo`,
`sequence`, or `double_tap`); localized title and description; category;
scope; application identities; recommendation and rank; provenance;
visibility; builtin/user origin; and aliases. `ShortcutPack` adds schema
version, pack/product identity, application aliases, platform/locales, source
metadata, and ordered entries.

External packs are optional JSON files in `config/shortcut_packs/`. Files load
in deterministic path order. Invalid JSON, unsupported schema, malformed
URLs, duplicate IDs, invalid application aliases, and duplicate pack IDs are
recorded as load issues and skipped; a bad optional pack cannot prevent the
legacy catalog from starting.

Pack provenance must contain a human-readable title and an `http` or `https`
URL. This is enough to retain source attribution without importing any source
at runtime.

## Compatibility adapter and resolver boundary

The existing `shortcuts.json` remains the source of truth in this phase. Its
entries are converted at startup into deterministic IDs of the form
`legacy:<scope>:<application>:<modifier>:<key>`. Original descriptions are
retained verbatim, including existing `{en, zh}` values; the Catalog view also
exposes `zh_CN` for that legacy Chinese value.

`CatalogShortcutResolver` is the new runtime boundary. It converts effective
Catalog entries back to the established `ShortcutEntry` contract consumed by
the HUD. It intentionally preserves the legacy priority and first-key-wins
rules:

```
USER_APP > APP > DEFAULT > GLOBAL
```

A known application with no entries for a held modifier still does not fall
back to `DEFAULT`; it may only contribute `GLOBAL`, exactly as before. Legacy
hidden builtins and user overrides retain their current identity matching.
Legacy multi-stroke rows remain displayable through their legacy adapter
metadata, although the current HUD continues to be modifier-triggered only.

The old editor and `UserShortcutStore` remain unchanged. User-created rows are
adapted into runtime `USER_APP` entries rather than migrated on disk. This
avoids a destructive schema migration and keeps the current editor safe.

## Selection ownership

Quick HUD selection is a separate, atomic per-user document:
`%APPDATA%/ShortcutHUD/quick_hud_selection.json` (with an explicit environment
override for tests and development). It stores selected Catalog IDs by
application identity. An absent selection uses each entry's `recommended`
default. An explicit selection overrides that default. No selection UI is
introduced in this phase, so existing users have no new file and see the same
legacy rows: legacy and adapted user entries are recommended by default.

Keeping selections out of packs and out of `user_shortcuts.json` prevents a
pack update from overwriting preference and prevents a preference write from
rewriting source data.

## Scope and non-goals

The runtime still displays only effective modifier/combination entries. It
does not add a catalog browser, search, Guide, command surface, learning
system, downloader, large shortcut data set, or an automatic migration UI.
`sequence` and `double_tap` are modeled so future surfaces do not have to
invent another data schema; the Quick HUD deliberately ignores them today.

## Risks and mitigations

- Catalog IDs are now a compatibility contract. Legacy IDs are derived from
  normalized logical inputs, not random values.
- Optional packs must never replace legacy data; the loader fails closed per
  file and logs a specific issue.
- Resolver ordering is visible in the small HUD. Tests compare adapter output
  with the legacy resolver and retain conflict, hidden-builtin, global, and
  known-app semantics.
- Full Catalog fields are not yet rendered. The compatibility output is kept
  intentionally narrow until a separately scoped UI phase is approved.
