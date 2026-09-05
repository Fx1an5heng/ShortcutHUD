# Shortcut Library v1

## A checkbox needed more than a boolean

Catalog Foundation already had a selection store, but the important product
edge was still unresolved: a missing value and an empty list are not the same
user intent. Treating both as “recommended” would make Clear All impossible;
treating both as “nothing” would hide the initial product defaults. The Library
keeps this distinction all the way from UI button to persisted JSON to HUD
resolver.

That also exposed a layering detail. Application selection should not change
the shared GLOBAL layer. The resolver now filters selected app/default/user
records while preserving global output. This makes Clear All mean what the
dialog says without quietly changing global shortcut behavior.

## A formal Pack must be able to replace a legacy view

The first implementation simply appended Pack entries to adapted legacy data.
For CODE.EXE that made every legacy entry recommended, defeating the Pack's
curated default and creating duplicate shortcut identities. The final Catalog
view masks only legacy builtin APP rows for an identity supplied by a formal
builtin Pack. It does not affect Edge, Explorer, WPS, Terminal, DEFAULT,
GLOBAL, or USER rows.

## Stable migration without guessing

The pre-UI adapter IDs are useful compatibility IDs but not the permanent VS
Code naming scheme. `id_aliases` provides a short, inspectable bridge from
known `legacy:*` IDs to formal Pack IDs. The selection store maps only declared
aliases and ignores unknown IDs. There is no description matching, position
matching, or automatic cleanup that could silently select the wrong command.

## UI shape

The Library is a compact modal dialog reached from Settings > Shortcuts. It
uses an application selector, immediate in-memory filtering, and a four-column
table rather than a card grid. The application title comes from Pack product
metadata when present, not an executable path. Every checkbox action is
immediately atomically persisted; Restore Recommended and Clear All state
their different effects in code as well as in the UI.

## Pilot data and verification

The VS Code pilot has 41 representative Windows entries sourced from the
official default keyboard shortcut reference and keybindings documentation.
The Pack includes Simplified Chinese descriptions, official HTTPS provenance,
categories and aliases for search, deterministic ranks, and eight recommended
defaults. Automated coverage checks the selection contract, persistence,
stale IDs, declared ID migration, Pack identity and provenance, Chinese and
English search, aliases/categories/triggers, model checkbox behavior, user
entry coexistence, and resolver precedence.

Deferred work remains deliberately product-scoped: a Full Guide, bulk command
import, online Pack updates, a marketplace, search result highlighting, and
any large-corpus data work are not part of Shortcut Library v1.

## UX correction: product names and current context

The first Windows smoke test exposed an architectural gap: the dialog had
reused Catalog entries but still made its own temporary application list. That
left product labeling inconsistent, did not make the existing last-valid
external application available to the dialog, and made formal Pack discovery
too easy to regress.

The correction added a Catalog-facing application registry rather than a new
foreground detector. It merges formal Packs, legacy entries, and user profiles
into products with a friendly display name and matching identities. Settings
passes the same `CurrentApplicationCandidateTracker` fact already used by Game
Guard, so opening Settings cannot replace a VS Code candidate with
ShortcutHUD's own process. The selector presents Current Application, Recent /
Detected Applications, and All Supported Applications; process names are not
normal user-facing labels and the internal `legacy` category becomes Other.

The UI labels were added to the existing Qt translation source and compiled
into the shipped `zh_CN` resource. Automated translation assertions cover the
major Library labels, alongside Pack/legacy registry merging and current-app
selection. Search intentionally remains while changing applications: it makes
cross-application comparison fast, and the table simply recalculates against
the newly selected product rather than treating an empty result as an error.
