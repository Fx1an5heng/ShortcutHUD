# Shortcut Pack sources: PowerToys audit

Audit date: 2026-09-07. Upstream snapshot: Microsoft PowerToys
`47f0e4db5af8c399a1a1456005b2e42e0d04293e`.

PowerToys Shortcut Guide ships YAML files under
`src/modules/ShortcutGuide/ShortcutGuide.Ui/Assets/ShortcutGuide/Manifests/`.
The audited schema uses `PackageName`, `Name`, `WindowFilter`,
`BackgroundProcess`, and `Shortcuts`; every section has `SectionName` and
`Properties`, whose records include `Name`, optional `Description` and
`Recommended`, plus a `Shortcut` array of modifier booleans and `Keys`.

ShortcutHUD maps an exact executable `WindowFilter` to application identity,
sections to stable category slugs, one stroke to a combo, and multiple strokes
to a future `sequence`. Wildcard/background manifests, no-modifier strokes,
multi-terminal-key strokes and unsupported symbolic keys are reported rather
than guessed. Duplicate Quick HUD combinations are retained as full-guide-only
Catalog records until command context can be represented.

The source contains English text only for the audited files. ShortcutHUD emits
native localized JSON Packs and carries its own Chinese wording, stable IDs,
coverage and provenance. PowerToys' `Recommended` is capped at ten Quick HUD
defaults per Pack; it is input to curation, not an unlimited product default.

The PowerToys root repository is MIT-licensed. We do not vendor its repository
or use it at runtime. Generated Packs record repository, revision, manifest and
MIT provenance; the notice is retained in `THIRD_PARTY_NOTICES.md`.

Sources: [PowerToys manifests](https://github.com/microsoft/PowerToys/tree/main/src/modules/ShortcutGuide/ShortcutGuide.Ui/Assets/ShortcutGuide/Manifests),
[PowerToys LICENSE](https://github.com/microsoft/PowerToys/blob/main/LICENSE),
[Shortcut Guide documentation](https://learn.microsoft.com/en-us/windows/powertoys/shortcut-guide).
