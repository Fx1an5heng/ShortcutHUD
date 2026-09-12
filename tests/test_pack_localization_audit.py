"""Shipping Chinese is reviewed exact text; the audit remains warning-only."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_pack_localization import audit_directory, audit_pack, english_tokens
from polish_shortcut_packs import polish_pack


class PackLocalizationAuditTests(unittest.TestCase):
    def test_all_eight_shipping_packs_have_no_unreviewed_latin_tokens(self):
        report = audit_directory(ROOT / "config/shortcut_packs")
        self.assertEqual(report["reviewed_entries"], 574)
        self.assertEqual(report["warning_count"], 0)

    def test_accidental_mixed_translation_is_reported(self):
        report = audit_pack({"id": "bad", "product": {"zh_CN": "示例"}, "categories": {}, "entries": [{"id": "bad.row", "title": {"zh_CN": "显示 Problems"}, "description": {"zh_CN": "Quick 打开"}}]})
        self.assertEqual(len(report["warnings"]), 2)
        self.assertEqual(report["warnings"][0]["tokens"], ("Problems",))

    def test_intentional_product_and_technical_terms_are_allowed(self):
        for text in ("Visual Studio Code", "打开 Git 仓库", "编辑 JSON 文件", "切换 Markdown 预览", "启动 PowerShell"):
            self.assertEqual(english_tokens(text), (), text)

    def test_known_vscode_samples_are_natural_chinese(self):
        pack = json.loads((ROOT / "config/shortcut_packs/vscode.json").read_text(encoding="utf8"))
        expected = {
            "Show All Commands (Command Palette)": "显示所有命令",
            "Quick Open / Go to File": "快速打开文件",
            "Open Keyboard Shortcuts": "打开键盘快捷方式",
            "Go to Line": "转到行",
            "Go to Symbol": "转到符号",
            "Show Problems": "显示问题",
            "Go to Next Error or Warning": "转到下一个错误或警告",
            "Replace in Files": "在文件中替换",
            "Show Source Control": "显示源代码管理",
        }
        actual = {entry["title"]["en"]: entry["title"]["zh_CN"] for entry in pack["entries"]}
        self.assertTrue(expected.items() <= actual.items())

    def test_english_ids_triggers_aliases_and_order_survive_polish(self):
        translations = json.loads((ROOT / "tools/shortcut_pack_zh_cn.json").read_text(encoding="utf8"))
        review = json.loads((ROOT / "tools/shortcut_pack_presentation_review.json").read_text(encoding="utf8"))
        for name in review["packs"]:
            original = json.loads((ROOT / f"config/shortcut_packs/{name}.json").read_text(encoding="utf8"))
            polished = polish_pack(original, translations, review)
            self.assertEqual(polished, original, name)  # idempotent
            for left, right in zip(original["entries"], polished["entries"]):
                for field in ("id", "trigger", "id_aliases", "aliases", "rank"):
                    self.assertEqual(left.get(field), right.get(field), (name, field))
                self.assertEqual(left["title"]["en"], right["title"]["en"])
                self.assertEqual(left["description"]["en"], right["description"]["en"])
