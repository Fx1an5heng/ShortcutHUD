# Shortcut Pack Expansion v1

PowerToys' current Shortcut Guide manifests supplied the structured baseline
for VS Code, Windows Terminal, Chrome, Edge, File Explorer, Word, Excel and
PowerPoint. The real schema stores sequential strokes in one `Shortcut` array;
the importer preserves these as future Catalog sequences instead of flattening
them into false combos.

The first generator bug split a literal `+` terminal key while re-parsing a
display string. Validator coverage caught the empty key before any Pack was
accepted. The importer now keeps structured stroke tokens to serialization.
The upstream source also includes no-modifier and symbolic-range controls that
ShortcutHUD cannot safely show in its modifier HUD; they are explicitly
reported, not fabricated.

The output is native JSON with provenance, coverage and localized text. The
temporary upstream checkout is only an audit input and is not committed.

## Full Guide boundary correction

Review caught a future-facing data loss before Full Guide existed: the importer
had treated "the Quick HUD cannot show this" as "the Catalog cannot contain
this". That hid valid F-keys and sequence shortcuts from every later surface.
The correction added a `single` trigger and an explicit Quick HUD capability
test. Shortcut Center now browses these records but disables their selection
checkbox; the existing keyboard handler and modifier HUD protocol are
unchanged.

The original 73 deferred records were audited rather than relabeled: 52 were
simple unmodified keys, 9 were sequences with an unmodified stroke, 5 were
range/family notation, and 7 were duplicate Quick HUD combinations. There
were no unknown source forms. The single-key, sequence, and duplicate groups
are now native Pack entries, with duplicate records retained as full-guide-only.
The five range records remain rejected because `<Arrow>` and `Number (1-9)` do not
provide enough semantics for a safe deterministic expansion.

The regeneration exposed a second issue: substring replacement corrupted
Chinese strings (for example `Browse` through the `row` glossary entry). The
localization rule is now phrase-first and whole-word bounded. A review sampled
ordinary rows, recommended rows, and every category in all eight Packs; common
Windows, Office, browser, VS Code, and Terminal actions now use concise
product-appropriate Chinese rather than mixed-word fragments.
