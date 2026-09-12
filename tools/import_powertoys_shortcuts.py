"""Convert one PowerToys Shortcut Guide YAML manifest into a native JSON Pack.

This is a development-time tool.  ShortcutHUD never reads PowerToys files at
runtime.  See ``--help`` for the explicitly supplied product metadata required
to make the resulting Pack shippable.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

import yaml


class ManifestImportError(ValueError):
    """The upstream document cannot be converted without guessing."""


@dataclass(frozen=True)
class ImportResult:
    pack: dict[str, Any]
    unsupported: tuple[str, ...]
    catalog_only: tuple[str, ...]
    upstream_entries: int


_KEY_NAMES = {
    "comma": ",", "period": ".", "slash": "/", "tilde": "`",
    "plus": "+", "minus": "-", "backslash": "\\",
    "leftbracket": "[", "rightbracket": "]",
}
_SPECIAL_KEYS = {
    "enter": "Enter", "space": "Space", "tab": "Tab",
    "backspace": "Backspace", "delete": "Delete", "insert": "Insert",
    "home": "Home", "end": "End", "pageup": "PageUp",
    "pagedown": "PageDown", "escape": "Esc", "left": "Left",
    "right": "Right", "up": "Up", "down": "Down", "prtscr": "PrintScreen",
    "pause": "Pause",
}
_MODIFIERS = (("Win", "Win"), ("Ctrl", "Ctrl"), ("Shift", "Shift"), ("Alt", "Alt"))


def load_manifest(path: str | Path) -> Mapping[str, Any]:
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ManifestImportError(f"cannot read YAML manifest: {error}") from error
    if not isinstance(document, Mapping):
        raise ManifestImportError("manifest root must be a mapping")
    return document


def convert_manifest(
    document: Mapping[str, Any], *, pack_id: str, product: Mapping[str, str],
    app_identities: list[str], aliases: list[str], official_reference_url: str,
    official_reference_title: str, upstream_revision: str, coverage: str = "substantial",
    recommended_limit: int = 10, translation_map: Mapping[str, str] | None = None,
    existing_pack: Mapping[str, Any] | None = None,
) -> ImportResult:
    """Return deterministic Pack data and explicit non-representable records."""

    package = _text(document.get("PackageName"), "PackageName")
    name = _text(document.get("Name"), "Name")
    window_filter = _text(document.get("WindowFilter"), "WindowFilter")
    if document.get("BackgroundProcess", False) is not False:
        raise ManifestImportError("BackgroundProcess manifests are not app-scoped Packs")
    if window_filter == "*" or not window_filter.casefold().endswith(".exe"):
        raise ManifestImportError("WindowFilter must be one exact executable name")
    if not isinstance(document.get("Shortcuts"), list):
        raise ManifestImportError("Shortcuts must be an array")
    if coverage not in {"partial", "substantial", "verified_complete"}:
        raise ManifestImportError("coverage must be partial, substantial, or verified_complete")
    if recommended_limit < 0:
        raise ManifestImportError("recommended_limit must not be negative")
    translations = dict(translation_map or {})
    existing_document = existing_pack or {}
    old_ids = _existing_ids_by_title_and_combo(existing_document)
    existing_categories = existing_document.get("categories", {}) if isinstance(existing_document, Mapping) else {}
    unsupported: list[str] = []
    catalog_only: list[str] = []
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set(); seen_quick_triggers: set[tuple[str, ...]] = set(); existing_by_trigger: dict[tuple[str, ...], dict[str, Any]] = {}
    for raw_entry in existing_document.get("entries", ()) if isinstance(existing_document, Mapping) else ():
        if not isinstance(raw_entry, Mapping): continue
        entry = json.loads(json.dumps(raw_entry)); seen_ids.add(entry.get("id", ""))
        trigger = entry.get("trigger", {}); keys = trigger.get("keys") if isinstance(trigger, Mapping) else None
        if trigger.get("kind") == "combo" and isinstance(keys, list) and "quick_hud" in entry.get("visibility", ()):
            trigger_key = tuple(keys)
            if trigger_key in seen_quick_triggers:
                entry["visibility"] = [item for item in entry["visibility"] if item != "quick_hud"] or ["full_guide"]
                first = existing_by_trigger[trigger_key]; first.setdefault("id_aliases", []).append(entry["id"])
            else:
                seen_quick_triggers.add(trigger_key); existing_by_trigger[trigger_key] = entry
        elif "quick_hud" in entry.get("visibility", ()):
            entry["visibility"] = [item for item in entry["visibility"] if item != "quick_hud"] or ["full_guide"]
        entries.append(entry)
    upstream_recommended = 0
    upstream_entries = 0
    for section_index, section in enumerate(document["Shortcuts"]):
        if not isinstance(section, Mapping):
            raise ManifestImportError(f"Shortcuts[{section_index}] must be a mapping")
        section_name = _text(section.get("SectionName"), f"Shortcuts[{section_index}].SectionName")
        properties = section.get("Properties")
        if not isinstance(properties, list):
            raise ManifestImportError(f"section {section_name!r} Properties must be an array")
        category = _category_key(section_name, existing_categories)
        for property_index, property_data in enumerate(properties):
            if not isinstance(property_data, Mapping):
                raise ManifestImportError(f"{section_name}[{property_index}] must be a mapping")
            action = _text(property_data.get("Name"), f"{section_name}[{property_index}].Name")
            upstream_entries += 1
            trigger, reason = _convert_trigger(property_data.get("Shortcut"))
            if reason:
                unsupported.append(f"{section_name} / {action}: {reason}")
                continue
            assert trigger is not None
            upstream_marked = property_data.get("Recommended", False)
            if not isinstance(upstream_marked, bool):
                raise ManifestImportError(f"{section_name} / {action}: Recommended must be boolean")
            quick_visible = trigger["kind"] == "combo"
            trigger_key = tuple(trigger["keys"])
            if quick_visible and trigger_key in seen_quick_triggers:
                # Center has no command-context disambiguation yet; retain the record
                # as future data rather than letting a duplicate silently win in HUD.
                quick_visible = False
                catalog_only.append(f"{section_name} / {action}: duplicate Quick HUD trigger retained as full-guide-only")
            elif not quick_visible:
                catalog_only.append(f"{section_name} / {action}: {trigger['kind']} trigger retained as full-guide-only")
            if quick_visible:
                seen_quick_triggers.add(trigger_key)
            recommended = bool(upstream_marked and quick_visible and upstream_recommended < recommended_limit)
            if recommended:
                upstream_recommended += 1
            semantic = _slug(action)
            prior_id = old_ids.get((semantic, trigger_key))
            stable_id = prior_id if prior_id is not None and prior_id not in seen_ids else _stable_id(pack_id, semantic, trigger_key, seen_ids)
            seen_ids.add(stable_id)
            zh_action = _required_translation(translations, action)
            english_description = _text_or(action, property_data.get("Description"))
            entries.append({
                "id": stable_id,
                "trigger": trigger,
                "title": {"en": action, "zh_CN": zh_action},
                "description": {"en": english_description, "zh_CN": _required_translation(translations, english_description)},
                "category": category,
                "scope": "app",
                "recommended": recommended,
                "rank": len(entries) + 1,
                "provenance": {
                    "title": "PowerToys Shortcut Guide manifest",
                    "url": f"https://github.com/microsoft/PowerToys/blob/{upstream_revision}/src/modules/ShortcutGuide/ShortcutGuide.Ui/Assets/ShortcutGuide/Manifests/{package}.en-US.yml",
                    "source_type": "PowerToys bundled manifest", "upstream_package": package,
                    "upstream_revision": upstream_revision,
                },
                "visibility": ["quick_hud", "full_guide"] if quick_visible else ["full_guide"],
                "builtin": True,
                "aliases": [],
            })
    categories = dict(existing_categories)
    for section in document["Shortcuts"]:
        if not isinstance(section, Mapping): continue
        section_name = _text(section.get("SectionName"), "SectionName")
        categories.setdefault(_category_key(section_name, existing_categories), {
            "en": section_name,
            "zh_CN": _required_translation(translations, section_name),
        })
    return ImportResult({
        "schema_version": 1, "id": pack_id, "product": dict(product),
        "app_identities": app_identities, "aliases": aliases, "platforms": ["windows"],
        "locales": ["en", "zh_CN"],
        "source": {"title": "Microsoft PowerToys Shortcut Guide", "url": "https://github.com/microsoft/PowerToys", "license": "MIT", "revision": upstream_revision, "manifest": package},
        "coverage": {"status": coverage, "official_reference_title": official_reference_title, "official_reference_url": official_reference_url, "verified_date": "2026-09-07"},
        "categories": categories, "entries": entries,
    }, tuple(unsupported), tuple(catalog_only), upstream_entries)


def _convert_trigger(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(raw, list) or not raw:
        return None, "Shortcut must be a non-empty array"
    strokes: list[tuple[str, ...]] = []
    for stroke in raw:
        if not isinstance(stroke, Mapping) or not all(isinstance(stroke.get(name), bool) for name, _ in _MODIFIERS):
            return None, "each stroke needs boolean Win/Ctrl/Shift/Alt"
        keys = stroke.get("Keys")
        if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], (str, int)):
            return None, "each stroke must contain exactly one terminal key"
        key = _key(keys[0])
        if key is None:
            return None, f"unsupported key representation: {keys[0]!r}"
        modifiers = [display for field, display in _MODIFIERS if stroke[field]]
        strokes.append(tuple((*modifiers, key)))
    if len(strokes) == 1:
        if len(strokes[0]) == 1:
            return {"kind": "single", "keys": list(strokes[0])}, None
        return {"kind": "combo", "keys": list(strokes[0])}, None
    return {"kind": "sequence", "keys": ["+".join(stroke) for stroke in strokes]}, None


def _key(value: str | int) -> str | None:
    if isinstance(value, int):
        return None
    token = value.strip()
    if token.startswith("<") and token.endswith(">"):
        token = token[1:-1]
    if len(token) == 1 and token.isprintable():
        return token.upper() if token.isalpha() else token
    if re.fullmatch(r"F(?:[1-9]|[12][0-9]|3[0-5])", token, flags=re.I):
        return token.upper()
    return _KEY_NAMES.get(token.casefold()) or _SPECIAL_KEYS.get(token.casefold())


def _existing_ids_by_title_and_combo(pack: Mapping[str, Any]) -> dict[tuple[str, tuple[str, ...]], str]:
    result: dict[tuple[str, tuple[str, ...]], str] = {}
    for entry in pack.get("entries", ()) if isinstance(pack, Mapping) else ():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("id"), str) or not isinstance(entry.get("trigger"), Mapping):
            continue
        trigger = entry["trigger"]
        title = entry.get("title")
        title_en = title.get("en") if isinstance(title, Mapping) else None
        if trigger.get("kind") == "combo" and isinstance(trigger.get("keys"), list) and isinstance(title_en, str):
            result.setdefault((_slug(title_en), tuple(trigger["keys"])), entry["id"])
    return result


def _stable_id(pack_id: str, semantic: str, trigger: tuple[str, ...], seen: set[str]) -> str:
    candidate = f"{pack_id.split('.', 1)[0]}.{semantic}"
    if candidate not in seen:
        return candidate
    digest = sha256("\x1f".join(trigger).encode("utf-8")).hexdigest()[:8]
    return f"{candidate}.{digest}"


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    return value or "shortcut"


def _category_key(section_name: str, existing_categories: Mapping[str, Any]) -> str:
    target = _slug(section_name)
    for key, labels in existing_categories.items():
        if isinstance(key, str) and isinstance(labels, Mapping) and _slug(str(labels.get("en", ""))) == target:
            return key
    return target


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestImportError(f"{name} must be a non-empty string")
    return value.strip()


def _text_or(fallback: str, value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback




def _required_translation(translations: Mapping[str, str], text: str) -> str:
    """Shipping localization is exact and reviewed; partial synthesis is forbidden."""
    translated = translations.get(text)
    if not isinstance(translated, str) or not translated.strip():
        raise ManifestImportError(f"missing exact zh_CN translation for {text!r}")
    return translated.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack-id", required=True); parser.add_argument("--product-en", required=True); parser.add_argument("--product-zh", required=True)
    parser.add_argument("--app-identity", action="append", required=True); parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--official-reference-title", required=True); parser.add_argument("--official-reference-url", required=True); parser.add_argument("--upstream-revision", required=True)
    parser.add_argument("--translations", type=Path, required=True); parser.add_argument("--existing-pack", type=Path); parser.add_argument("--report", type=Path); parser.add_argument("--coverage", default="substantial"); parser.add_argument("--recommended-limit", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        translations = json.loads(args.translations.read_text(encoding="utf-8")); existing = json.loads(args.existing_pack.read_text(encoding="utf-8")) if args.existing_pack else None
        result = convert_manifest(load_manifest(args.manifest), pack_id=args.pack_id, product={"en": args.product_en, "zh_CN": args.product_zh}, app_identities=args.app_identity, aliases=args.alias, official_reference_url=args.official_reference_url, official_reference_title=args.official_reference_title, upstream_revision=args.upstream_revision, coverage=args.coverage, recommended_limit=args.recommended_limit, translation_map=translations, existing_pack=existing)
    except (ManifestImportError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr); return 2
    args.output.write_text(json.dumps(result.pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = {
        "upstream_entries": result.upstream_entries,
        "imported_entries": len(result.pack["entries"]),
        "catalog_only": list(result.catalog_only),
        "unsupported": list(result.unsupported),
    }
    if args.report: args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
