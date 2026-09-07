# Shortcut Pack import pipeline

Pack data is generated at development time from an audited source, validated,
then shipped as native JSON. Runtime code never downloads, scans or depends on
PowerToys. Official vendor references outrank PowerToys manifests; the latter
provide a reproducible structured source when their quality is adequate.

Stable IDs use product namespace plus a semantic slug. A collision receives a
deterministic trigger hash. VS Code imports reuse old IDs only when both title
slug and combo match; selections remain external state and aliases remain the
only permitted migration mechanism.

All shipping text requires English and Simplified Chinese. Coverage is explicit:
`partial`, `substantial`, or `verified_complete`; this first expansion uses
`substantial` only where an audited source exists, never claims completeness.
`tools/validate_shortcut_packs.py` audits schema, source, coverage, locales,
IDs, aliases and Quick HUD trigger conflicts.

## Catalog completeness is independent of Quick HUD capability

A Pack describes the application's shortcut catalog, not only the subset that
the current modifier-held Quick HUD can render. A one-key trigger such as
`F5`, a sequence such as `Ctrl+K Ctrl+S`, and a future `double_tap` are valid
Catalog records. They remain visible in Shortcut Center and are marked
`full_guide` only; only a modifier-driven `combo` may carry `quick_hud` today.
The importer reports these as `catalog_only`, never as skipped.

The old 73-item report mixed those concepts: 52 ordinary unmodified keys, 9
sequences containing an unmodified stroke, 5 range/family notations, and 7
duplicate Quick HUD combinations. The first, second and fourth groups are now
imported. The 5 range records (`<Arrow>` and `Number (1-9)`) remain truly
unsupported because the manifests do not state a single unambiguous concrete
shortcut or its expansion semantics. Guessing four arrows, or nine number
keys, would invent data. Unsupported therefore now means only a source/schema
form that Catalog cannot reliably represent.

The generator uses phrase-first localization followed by bounded whole-word
glossary replacement. This prevents partial-word corruption such as replacing
`row` inside `Browse`; source-specific overrides still take precedence.
