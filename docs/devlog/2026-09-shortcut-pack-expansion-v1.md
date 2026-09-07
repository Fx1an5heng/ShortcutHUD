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
