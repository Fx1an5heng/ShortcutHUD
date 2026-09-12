"""Development-only Chinese quality warnings; never gates runtime loading."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ALLOWED_TERMS = frozenset({
    "VS Code", "Visual Studio Code", "Visual Basic", "Windows Terminal",
    "Git", "JSON", "HTML", "CSS", "Markdown", "GitHub", "URL", "HTTP", "HTTPS",
    "Terminal", "PowerShell", "JavaScript", "TypeScript", "IntelliSense",
    "Chrome", "Edge", "InPrivate", "Windows", "Word", "Excel", "PowerPoint",
    "Google", "Microsoft",
    "AI", "SQL", "Python", "UTF-8", "www", "com",
})
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-.+#][A-Za-z0-9]+)*")


def english_tokens(text: str) -> tuple[str, ...]:
    remaining = text
    for term in sorted(ALLOWED_TERMS, key=lambda value: (-len(value), value)):
        remaining = re.sub(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", "", remaining, flags=re.I)
    return tuple(sorted(set(_LATIN_TOKEN.findall(remaining))))


def localized_fields(pack):
    yield "product", pack.get("product", {})
    for category, value in pack.get("categories", {}).items():
        yield f"category:{category}", value
    for entry in pack.get("entries", ()):
        for field in ("title", "description"):
            yield f'{entry["id"]}:{field}', entry.get(field, {})


def audit_pack(pack):
    warnings = []
    intentional = set()
    for field, localized in localized_fields(pack):
        text = localized.get("zh_CN", "") if isinstance(localized, dict) else ""
        tokens = english_tokens(text)
        if not text or tokens:
            warnings.append({"pack": pack.get("id"), "field": field, "text": text, "tokens": tokens})
        for term in ALLOWED_TERMS:
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", text, re.I):
                intentional.add(term)
    return {"reviewed_entries": len(pack.get("entries", ())), "warnings": warnings, "intentional_terms": sorted(intentional)}


def audit_directory(directory):
    results = {path.stem: audit_pack(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(Path(directory).glob("*.json"))}
    return {"reviewed_entries": sum(item["reviewed_entries"] for item in results.values()),
            "warning_count": sum(len(item["warnings"]) for item in results.values()), "packs": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    report = audit_directory(args.directory)
    if not args.details:
        for result in report["packs"].values():
            result["warnings"] = len(result["warnings"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Warnings are a review aid, not a translation correctness proof or gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
