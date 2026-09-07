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
