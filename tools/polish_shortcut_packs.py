"""Apply reviewed exact text and presentation metadata; no importing or ID edits."""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def polish_pack(pack, translations, review, *, localization=True):
    result = deepcopy(pack)
    semantic_ids = {identifier: group[0] for group in review["equivalences"] for identifier in group}
    for entry in result["entries"]:
        if entry["id"] in semantic_ids:
            entry["provenance"]["presentation_semantic_id"] = semantic_ids[entry["id"]]
        english = entry["title"]["en"]
        # These labels were reviewed against the shipping legacy adapter;
        # runtime equivalence ALSO requires app + full trigger + context.
        labels = review["legacy_titles"].get(english, [])
        if labels:
            entry["provenance"]["presentation_legacy_titles"] = labels
        if localization:
            for field in ("title", "description"):
                entry[field]["zh_CN"] = translations[entry[field]["en"]]
    if localization:
        for labels in result["categories"].values():
            labels["zh_CN"] = translations[labels["en"]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--write", action="store_true", help="Apply to shipping Pack files only")
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    translations = json.loads((HERE / "shortcut_pack_zh_cn.json").read_text(encoding="utf8"))
    review = json.loads((HERE / "shortcut_pack_presentation_review.json").read_text(encoding="utf8"))
    for name in review["packs"]:
        path = args.directory / f"{name}.json"
        original = json.loads(path.read_text(encoding="utf8"))
        result = polish_pack(original, translations, review, localization=not args.metadata_only)
        if args.write and result != original:
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        print(f'{name}: {len(result["entries"])} records; {"changed" if result != original else "unchanged"}')


if __name__ == "__main__":
    main()
