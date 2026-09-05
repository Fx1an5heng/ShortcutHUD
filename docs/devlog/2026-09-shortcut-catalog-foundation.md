# Shortcut Catalog Foundation

## The real constraint was compatibility, not JSON shape

The first temptation was to replace `shortcuts.json` with a new list of rich
records. That would have produced a nicer document at the cost of changing
the live editor, user overrides, hidden-builtin state, and the compact HUD all
at once. More importantly, it would have made data migration the critical
path before there was a Catalog UI to justify it.

The investigation showed that current resolution has product behavior buried
in its ordering: a user row wins an app row, an app row wins a global row, a
known app missing a modifier does not fall back to `DEFAULT`, and the first
case-insensitive terminal key wins. That is the behavior users see, so the
foundation had to preserve it before adding any new metadata.

## The bridge

The implemented path is intentionally one-way for now. Legacy config is read
as before and adapted into ordered Catalog entries with deterministic IDs.
The new Catalog resolver then returns the exact small `ShortcutEntry` objects
that the HUD already understands. Existing user profiles are adapted in memory
as `USER_APP` records; their on-disk schema and editor stay untouched.

That separation made a useful boundary visible: data loading and validation
live in `shortcut_catalog.py`, effective display behavior lives in
`shortcut_catalog_resolver.py`, and the HUD remains a renderer. The controller
owns no shortcut database rules beyond asking the resolver for the current
foreground identity and modifier state.

## Packs are validated, not trusted

`config/shortcut_packs/` is present but intentionally contains no new shortcut
content. A pack declares schema version, product and application identities,
aliases, locales/platforms, source attribution, and structured entries. The
loader processes paths deterministically and skips only the bad file when it
finds malformed JSON, invalid metadata, or an identity collision. This is a
small detail with an important effect: a future contributed pack cannot take
the whole HUD down because one source file is broken.

## Preferences needed their own home

“Recommended” is a pack default; it is not a user decision. The foundation
therefore uses a separate, atomically written Quick HUD selection document.
Missing selection means recommended entries; an explicit selected-ID set wins.
There is no selector UI in this phase, so the default path preserves the full
legacy display. Keeping the file separate also prevents future pack refreshes
from rewriting preferences or shortcut editing from rewriting source metadata.

## What was deliberately left out

The model can store sequence and double-tap triggers, but the current runtime
continues to display only simple modifier combinations. No guide, catalog
browser, search, command center, learning, bulk shortcut corpus, download
service, or migration UI was added. Those are product phases, not a reason to
expand this compatibility layer.

## Verification

Focused coverage verifies legacy equivalence and deterministic IDs; user
override, hidden-builtin, and global conflict behavior; structured future
trigger parsing; app aliases; localization fallback; malformed and duplicate
packs; deterministic file loading; independent atomic selection persistence;
and explicit selection filtering. Existing HUD controller and user shortcut
integration coverage continues to exercise timer behavior, Win handling,
suppression, input recovery, and the legacy Quick HUD contract.
