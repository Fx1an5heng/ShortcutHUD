# Shortcut Library benchmark

Research completed before the Shortcut Library UX correction. This document
records product observations, not a code or data import.

## PowerToys Shortcut Guide

Microsoft's current Shortcut Guide opens on the foreground application, lists
the foreground plus matching background applications, groups shortcuts by
section, highlights recommendations, supports pinning, and searches shortcut
name, description, modifiers, and displayed keys. Its manifests are bundled
but it also accepts user YAML manifests. [Microsoft's current documentation](https://learn.microsoft.com/en-us/windows/powertoys/shortcut-guide)
describes `PackageName`, `Name`, `WindowFilter`, `BackgroundProcess`,
`SectionName`, `Recommended`, and the modifier/key structure.

Directly adopted:

- foreground application first, while keeping a manual supported-app browser;
- a compact current/recent/all application ordering instead of an installed
  software scan;
- categories and recommendations as data rather than UI rules;
- searching trigger and user-facing text.

Not adopted:

- a fullscreen reference window, pinning, and background-process discovery;
  ShortcutHUD's Library manages Quick HUD selection and is not a Full Guide;
- a dependency on PowerToys or its installation/user-manifest location.

PowerToys is MIT-licensed. Its source and manifest data can be evaluated for a
future opt-in importer only with required attribution/notice retained; this
phase neither copies its manifests nor puts its data on ShortcutHUD's runtime
path.

Potential mapping for a future `PowerToysShortcutManifestImporter`:

| PowerToys manifest | ShortcutHUD Pack |
| --- | --- |
| `PackageName`, `Name` | pack ID/product localized name (English source) |
| `WindowFilter` | application identity/alias matching |
| `BackgroundProcess` | future availability hint, not present detection |
| `SectionName` | category |
| `Recommended` | `recommended` |
| modifier booleans + `Keys` | structured combo/sequence trigger |
| manifest path/revision | provenance |

ShortcutHUD additionally requires formal stable IDs, `zh_CN` localization,
selection state, user overrides, and source provenance. Those cannot be
derived safely from a PowerToys display name alone. The mapping is structurally
clear, but a YAML parser/importer prototype is deferred so the UX correction
does not acquire a third-party data dependency.

## KeyClu

KeyClu emphasizes an application-specific overview and supplies a separate
“My Shortcuts” path when menu extraction cannot discover a shortcut; it also
documents known application limitations and sharing/export concepts. Its FAQ
shows the value of keeping user-owned shortcuts integrated with an application
view instead of a disconnected list. [KeyClu FAQ](https://github.com/Anze/KeyCluCask/wiki/FAQ)

Adopted: the Library includes existing USER shortcuts in the same app table.
Not adopted: macOS menu scraping, bookmark semantics, and external extension
collection. No KeyClu source or data is reused in ShortcutHUD.

## CheatKeys

CheatKeys centers the active application and hold-to-show interaction, while
also allowing custom shortcuts for unsupported apps. That reinforces
ShortcutHUD's current foreground-first Quick HUD model, but provides no public
manifest or source reuse path. [CheatKeys product page](https://cheatkeys.com/)

Adopted: active-app-first product framing. Not adopted: its trigger tuning,
global-toggle design, updater, or any proprietary code/data reuse.

## Resulting correction

ShortcutHUD now has one Catalog-facing application registry. It merges formal
packs, legacy-adapted applications, and user-supported applications; returns a
stable product ID, friendly display name, matching identities, source, and
detected state; and consumes the existing last-valid external application
tracker. Process identities remain matching details, not normal UI labels.

## Shortcut Center follow-up

This correction also adopts the foreground-first pattern more literally:
detected foreground applications are not filtered by shortcut coverage, and the
open Center follows the existing external-app signal until a user manually
chooses another application. Built-in and user-owned entries now share a table,
while the established recorder/editor remains the implementation behind USER
mutations. This retains the mature product pattern without copying a Full Guide
or creating a second application detector.
