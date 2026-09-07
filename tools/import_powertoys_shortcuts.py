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
            zh_action = translations.get(action) or _auto_translate(action)
            entries.append({
                "id": stable_id,
                "trigger": trigger,
                "title": {"en": action, "zh_CN": zh_action},
                "description": {"en": _text_or(action, property_data.get("Description")), "zh_CN": translations.get(_text_or(action, property_data.get("Description")), zh_action)},
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
            "zh_CN": translations.get(section_name) or _auto_translate(section_name),
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


def _auto_translate(text: str) -> str:
    """Apply deterministic, phrase-first Chinese localization to generated data.

    This deliberately is not a word-by-word translator.  The exact map handles
    frequently surfaced actions first, then a bounded glossary fills stable
    product terminology without replacing fragments inside unrelated words
    (for example, ``row`` inside ``Browse``).
    """

    exact = {
        "Open File Explorer": "打开文件资源管理器", "Select the address bar": "选择地址栏",
        "Select the search box": "选择搜索框", "Refresh the window": "刷新窗口",
        "Cycle through elements in the active window": "在活动窗口中的元素之间切换",
        "Maximize or restore the active window": "最大化或还原活动窗口",
        "Navigate to the previous folder": "转到上一个文件夹", "Navigate to the next folder": "转到下一个文件夹",
        "Create a new folder": "新建文件夹", "Open a new window": "打开新窗口", "Open a new tab": "打开新选项卡",
        "Display properties for the selected item": "显示所选项目的属性", "New incognito window": "新建无痕窗口",
        "Reopen previously closed tab": "重新打开最近关闭的选项卡", "Jump to next tab": "切换到下一个选项卡",
        "Jump to previous tab": "切换到上一个选项卡", "Jump to specific tab (1–8)": "切换到指定选项卡（1–8）",
        "Jump to rightmost tab": "切换到最右侧选项卡", "Open home page in current tab": "在当前选项卡打开主页",
        "Open previous page in history": "打开历史记录中的上一页", "Open next page in history": "打开历史记录中的下一页",
        "Turn full-screen mode on/off": "切换全屏模式", "Open split view in active tab": "在活动选项卡中打开拆分视图",
        "Open the Chrome menu": "打开 Chrome 菜单", "Show or hide bookmarks bar": "显示或隐藏书签栏",
        "Open Bookmarks Manager": "打开书签管理器", "Open Downloads page": "打开下载页面",
        "Open Chrome Task Manager": "打开 Chrome 任务管理器", "Find next match": "查找下一个匹配项",
        "Find previous match": "查找上一个匹配项", "Open Developer Tools (alt)": "打开开发者工具（备用）",
        "Print current page": "打印当前页面",
        "Clear Browsing Data": "清除浏览数据", "Open Help Center": "打开帮助中心",
        "Switch user / browse as guest": "切换用户或以访客身份浏览", "Open feedback form": "打开反馈表单",
        "Toggle caret browsing": "切换插入符浏览", "Jump to address bar": "转到地址栏",
        "Reopen the last closed tab": "重新打开最近关闭的选项卡", "Switch to the next tab": "切换到下一个选项卡",
        "Switch to the previous tab": "切换到上一个选项卡", "Switch to a specific tab": "切换到指定选项卡",
        "Switch to the last tab": "切换到最后一个选项卡", "Close the current tab": "关闭当前选项卡",
        "Close the current tab (alt)": "关闭当前选项卡（备用）", "Close the current window": "关闭当前窗口",
        "Close the current window (alt)": "关闭当前窗口（备用）", "New InPrivate window": "新建 InPrivate 窗口",
        "Duplicate the current tab": "复制当前选项卡", "Mute the current tab": "静音当前选项卡",
        "Switch to the next tab (alt)": "切换到下一个选项卡（备用）", "Switch to the previous tab (alt)": "切换到上一个选项卡（备用）",
        "Enter full screen": "进入全屏", "Select the URL in the address bar": "选择地址栏中的 URL",
        "Open a search query in the address bar": "在地址栏中打开搜索查询", "Paste and search or paste and go": "粘贴并搜索，或粘贴并转到",
        "Open Settings and more menu": "打开“设置及更多”菜单", "Open Downloads": "打开下载内容",
        "Open Collections": "打开集锦", "Open search in sidebar": "在侧边栏中打开搜索",
        "Show or hide the favorites bar": "显示或隐藏收藏夹栏", "Save the current tab as a favorite": "将当前选项卡保存为收藏夹",
        "Move focus to next pane": "将焦点移到下一个窗格", "Open find on page": "在页面中打开查找",
        "Copy": "复制", "Paste": "粘贴", "Save": "保存", "Open": "打开", "Find": "查找",
        "Redo or repeat last action": "重做或重复上一步操作", "Find and replace": "查找和替换",
        "Edit active cell": "编辑活动单元格", "AutoSum": "自动求和", "Move to beginning of worksheet": "移到工作表开头",
        "Open Go To dialog": "打开“转到”对话框", "Select entire worksheet": "选择整个工作表",
        "Select entire column": "选择整列", "Select entire row": "选择整行",
        "Turn extend mode on": "开启扩展模式", "Start a new line in the same cell": "在同一单元格中换行",
        "Open Format Cells dialog": "打开“设置单元格格式”对话框", "Strikethrough": "删除线",
        "Apply General number format": "应用常规数字格式", "Apply Currency format": "应用货币格式",
        "Apply Percentage format": "应用百分比格式", "Apply Date format": "应用日期格式",
        "Save As": "另存为", "Close PowerPoint": "关闭 PowerPoint", "Duplicate selected slide": "复制所选幻灯片",
        "Start slide show": "开始幻灯片放映", "Start Presenter view": "开始演示者视图",
        "End slide show": "结束幻灯片放映", "Zoom to fit": "缩放至适合窗口",
        "Select all objects": "选择所有对象", "Move to next cell": "移到下一个单元格",
        "Show or hide guides": "显示或隐藏参考线", "Show or hide grid": "显示或隐藏网格",
        "Toggle Outline and Thumbnail views": "切换大纲和缩略图视图", "Cycle through panes": "在窗格之间切换",
        "Open new tab dropdown": "打开新建选项卡下拉菜单", "Open settings UI": "打开设置界面",
        "Open settings JSON file": "打开设置 JSON 文件", "Open default settings file": "打开默认设置文件",
        "Toggle command palette": "切换命令面板", "Open system menu": "打开系统菜单",
        "Show command suggestions": "显示命令建议", "Duplicate current tab": "复制当前选项卡",
        "Close current pane": "关闭当前窗格", "Duplicate pane (horizontal split)": "复制窗格（水平拆分）",
        "Duplicate pane (vertical split)": "复制窗格（垂直拆分）", "Resize pane down": "向下调整窗格大小",
        "Resize pane up": "向上调整窗格大小", "Resize pane left": "向左调整窗格大小",
        "Resize pane right": "向右调整窗格大小", "Paste text only": "仅粘贴文本",
        "Cancel a command": "取消命令", "Go to": "转到", "Copy formatting": "复制格式",
        "Paste formatting": "粘贴格式", "Beginning of document": "文档开头", "End of document": "文档末尾",
        "Delete one word to the left": "删除左侧的一个单词", "Delete one word to the right": "删除右侧的一个单词",
        "Move one word to the left": "向左移动一个单词", "Move one word to the right": "向右移动一个单词",
        "Center": "居中", "Select word to the left": "选择左侧的单词", "Select word to the right": "选择右侧的单词",
        "Open Chat view": "打开聊天视图", "Trigger Suggest": "触发建议", "Run Build Task": "运行生成任务",
        "Copy to clipboard": "复制到剪贴板", "Scroll down one line": "向下滚动一行",
        "Increase font size": "增大字体大小", "Decrease font size": "减小字体大小",
    }
    if text in exact:
        return exact[text]

    phrases = {
        "Frequently used": "常用", "Tabs and windows": "选项卡和窗口", "Address bar": "地址栏",
        "Web page": "网页", "File management": "文件管理", "Window management": "窗口管理",
        "Basic editing": "基础编辑", "Rich languages editing": "富语言编辑", "Cell formatting": "单元格格式",
        "Character formatting": "字符格式", "Paragraph formatting": "段落格式", "Slide show and view": "幻灯片放映和视图",
        "Clipboard and selection": "剪贴板和选择", "Pane management": "窗格管理", "Tab management": "选项卡管理",
        "Application": "应用", "Navigation": "导航", "Selection": "选择", "Focus": "焦点",
        "Data entry and editing": "数据输入和编辑", "Formulas and functions": "公式和函数", "Tables": "表格",
        "Text editing": "文本编辑", "Text formatting": "文本格式", "Browser features": "浏览器功能",
        "Chrome features": "Chrome 功能", "Scrollback": "滚动缓冲区", "Font size": "字体大小",
        "Open ": "打开", "New ": "新建", "Close ": "关闭", "Save ": "保存", "Show ": "显示",
        "Hide ": "隐藏", "Toggle ": "切换", "Select ": "选择", "Move ": "移动", "Insert ": "插入",
        "Delete ": "删除", "Copy ": "复制", "Paste ": "粘贴", "Find ": "查找", "Replace": "替换",
        "current": "当前", "next": "下一个", "previous": "上一个", "last": "最后一个", "first": "第一个",
        "window": "窗口", "tab": "选项卡", "page": "页面", "file": "文件", "folder": "文件夹",
        "document": "文档", "workbook": "工作簿", "worksheet": "工作表", "slide": "幻灯片", "cell": "单元格",
        "selected": "所选", "all": "全部", "text": "文本", "search": "搜索", "result": "结果",
        "settings": "设置", "history": "历史记录", "address": "地址", "bar": "栏", "menu": "菜单",
        "full screen": "全屏", "full-screen": "全屏", "Zoom in": "放大", "Zoom out": "缩小", "Undo": "撤销", "Redo": "重做",
        "Bold": "加粗", "Italic": "斜体", "Underline": "下划线", "Print": "打印", "Cut": "剪切",
        "Paste Special": "选择性粘贴", "Developer Tools": "开发者工具", "Bookmarks": "书签", "Favorites": "收藏夹",
        "Reload": "重新加载", "Refresh": "刷新", "Back": "后退", "Forward": "前进", "Home": "主页",
        "Left": "左", "Right": "右", "Up": "上", "Down": "下", "Increase": "增大", "Decrease": "减小",
        "Reset": "重置", "Format": "格式", "formula": "公式", "chart": "图表", "table": "表格",
        "row": "行", "column": "列", "paragraph": "段落", "comment": "批注", "hyperlink": "超链接",
        "presentation": "演示文稿", "object": "对象", "view": "视图", "editor": "编辑器", "terminal": "终端",
        "command": "命令", "breakpoint": "断点", "debugging": "调试", "workspace": "工作区",
    }
    result = text
    for source, target in sorted(phrases.items(), key=lambda item: len(item[0]), reverse=True):
        suffix = r"(?![A-Za-z])" if source[-1].isalpha() else ""
        result = re.sub(r"(?<![A-Za-z])" + re.escape(source) + suffix, target, result, flags=re.IGNORECASE)
    return result


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
