"""Validate every shipping ShortcutHUD Pack without starting the UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.shortcut_catalog import CatalogValidationError, parse_shortcut_pack


def validate_directory(directory: str | Path) -> list[str]:
    errors: list[str] = []; seen_ids: set[str] = set(); alias_targets: set[str] = set()
    for path in sorted(Path(directory).glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            document = json.loads(path.read_text(encoding="utf-8")); pack = parse_shortcut_pack(document)
            _validate_shipping_locales(path, document); _validate_triggers(path, pack)
            for entry in pack.entries:
                if entry.id in seen_ids: errors.append(f"{path}: duplicate catalog id {entry.id}")
                seen_ids.add(entry.id); alias_targets.update(entry.id_aliases)
        except (OSError, UnicodeError, json.JSONDecodeError, CatalogValidationError, ValueError) as error:
            errors.append(f"{path}: {error}")
    unresolved = alias_targets - seen_ids
    errors.extend(f"id_alias target does not exist: {alias}" for alias in sorted(unresolved) if not alias.startswith("legacy:"))
    return errors


def _validate_shipping_locales(path: Path, document: object) -> None:
    if not isinstance(document, dict): return
    for label, item in [("product", document.get("product")), *[(f"category {key}", value) for key, value in (document.get("categories") or {}).items()]]:
        if not isinstance(item, dict) or not item.get("en") or not item.get("zh_CN"): raise ValueError(f"{label} requires en and zh_CN")
    for entry in document.get("entries", ()):
        if not isinstance(entry, dict): continue
        for label in ("title", "description"):
            text = entry.get(label)
            if not isinstance(text, dict) or not text.get("en") or not text.get("zh_CN"): raise ValueError(f"entry {entry.get('id')} {label} requires en and zh_CN")


def _validate_triggers(path: Path, pack: object) -> None:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for entry in pack.entries:
        trigger = (entry.trigger.kind, entry.trigger.keys)
        if trigger in seen and "quick_hud" in entry.visibility: raise ValueError(f"duplicate Quick HUD trigger {trigger}")
        if "quick_hud" in entry.visibility: seen.add(trigger)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("directory", type=Path); args = parser.parse_args(argv)
    errors = validate_directory(args.directory)
    for error in errors: print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__": raise SystemExit(main())
