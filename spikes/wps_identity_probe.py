"""Collect a bounded Win32 identity snapshot for the current foreground window.

This is an investigation-only spike. Production modules must not import it.
"""

from __future__ import annotations

import argparse
from collections import Counter
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
from typing import Any

import win32api
import win32con
import win32gui
import win32process


_MAX_DEPTH = 32
_WPS_PROCESS_NAMES = {
    "et.exe",
    "wps.exe",
    "wpsoffice.exe",
    "wpspdf.exe",
    "wpp.exe",
}
_WRITER_SIGNATURE_CLASSES = {
    "MsoCommandBar",
    "MsoCommandBarDock",
    "bosa_sdm_Microsoft Office Word 11.0",
    "_WwB",
    "_WwC",
    "_WwF",
    "_WwG",
}
_PDF_SIGNATURE_CLASSES = {
    "CefBrowserWindow",
    "Chrome_RenderWidgetHostHWND",
    "Chrome_WidgetWin_0",
    "KCefContainerWindow",
}
_PRESENTATION_SIGNATURE_CLASSES = {
    "MDIClient",
    "PP12FrameClass",
    "mdiClass",
}


def _bounded_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _hex(value: int) -> str:
    return f"0x{value & 0xFFFFFFFFFFFFFFFF:X}"

class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def _query_gui_thread_info(thread_id: int) -> dict[str, object]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    info = _GUITHREADINFO()
    info.cbSize = ctypes.sizeof(info)
    ctypes.set_last_error(0)
    success = bool(user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)))
    last_error = ctypes.get_last_error()
    current_thread_id = int(kernel32.GetCurrentThreadId())
    local_focus = int(user32.GetFocus() or 0)
    result: dict[str, object] = {
        "foreground_thread_id": thread_id,
        "probe_thread_id": current_thread_id,
        "get_focus_result": local_focus,
        "get_focus_scope": "probe_thread_only",
        "get_focus_cross_thread_limited": current_thread_id != thread_id,
        "get_gui_thread_info_status": "ok" if success else "failed",
    }
    if not success:
        result["last_error"] = last_error
        return result
    result.update(
        {
            "flags": _hex(int(info.flags)),
            "hwndActive": int(info.hwndActive or 0),
            "hwndFocus": int(info.hwndFocus or 0),
            "hwndCapture": int(info.hwndCapture or 0),
            "hwndMenuOwner": int(info.hwndMenuOwner or 0),
            "hwndMoveSize": int(info.hwndMoveSize or 0),
            "hwndCaret": int(info.hwndCaret or 0),
            "caret_rect": [
                int(info.rcCaret.left),
                int(info.rcCaret.top),
                int(info.rcCaret.right),
                int(info.rcCaret.bottom),
            ],
        }
    )
    return result


def _query_process_image(pid: int) -> tuple[str | None, str | None]:
    handle = None
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid,
        )
        return win32process.GetModuleFileNameEx(handle, 0), None
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"
    finally:
        if handle is not None:
            try:
                win32api.CloseHandle(handle)
            except Exception:
                pass


def _query_window_module(hwnd: int) -> dict[str, object]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    buffer = ctypes.create_unicode_buffer(32768)
    ctypes.set_last_error(0)
    length = user32.GetWindowModuleFileNameW(hwnd, buffer, len(buffer))
    if length:
        return {"value": buffer.value, "status": "ok"}
    return {
        "value": None,
        "status": "unavailable",
        "last_error": ctypes.get_last_error(),
    }


def _enum_window_properties(hwnd: int) -> dict[str, object]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    properties: list[dict[str, object]] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        wintypes.HWND,
        ctypes.c_void_p,
        wintypes.HANDLE,
        ctypes.c_size_t,
    )

    def callback(
        _window: int,
        name_pointer: int,
        value_handle: int,
        _data: int,
    ) -> int:
        pointer_value = int(name_pointer or 0)
        if 0 < pointer_value <= 0xFFFF:
            name = f"ATOM:{pointer_value}"
        elif pointer_value:
            try:
                name = ctypes.wstring_at(pointer_value)
            except Exception:
                name = f"POINTER:{_hex(pointer_value)}"
        else:
            name = "NULL"
        properties.append(
            {
                "name": name,
                "value": _hex(int(value_handle or 0)),
            }
        )
        return 1

    callback_ref = callback_type(callback)
    user32.EnumPropsExW.argtypes = [wintypes.HWND, callback_type, ctypes.c_size_t]
    user32.EnumPropsExW.restype = ctypes.c_int
    ctypes.set_last_error(0)
    result = user32.EnumPropsExW(hwnd, callback_ref, 0)
    last_error = ctypes.get_last_error()
    if result == -1:
        return {
            "status": "unsupported_or_failed",
            "last_error": last_error,
            "items": properties,
        }
    return {
        "status": "ok",
        "return_value": result,
        "item_count": len(properties),
        "items": properties,
    }


def _child_depth(child_hwnd: int, root_hwnd: int) -> int:
    depth = 0
    current = child_hwnd
    seen: set[int] = set()
    while current and current != root_hwnd and depth < _MAX_DEPTH:
        if current in seen:
            break
        seen.add(current)
        current = win32gui.GetParent(current)
        depth += 1
    return depth


def _window_rect(hwnd: int) -> list[int] | None:
    try:
        return [int(value) for value in win32gui.GetWindowRect(hwnd)]
    except Exception:
        return None


def _has_non_zero_rect(rect: list[int] | None) -> bool:
    return bool(rect and rect[2] > rect[0] and rect[3] > rect[1])


def _parent_chain(hwnd: int, root_hwnd: int) -> list[dict[str, object]]:
    chain: list[dict[str, object]] = []
    current = hwnd
    seen: set[int] = set()
    while current and current not in seen and len(chain) < _MAX_DEPTH:
        seen.add(current)
        try:
            chain.append(
                {
                    "hwnd": current,
                    "class_name": win32gui.GetClassName(current),
                    "is_root": current == root_hwnd,
                }
            )
        except Exception as error:
            chain.append(
                {
                    "hwnd": current,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
        if current == root_hwnd:
            break
        current = win32gui.GetParent(current)
    return chain


def _active_mdi_child(hwnd: int, class_name: str) -> int | None:
    if class_name != "MDIClient":
        return None
    try:
        return int(win32gui.SendMessage(hwnd, 0x0229, 0, 0) or 0)
    except Exception:
        return None


def _collect_children(
    hwnd: int,
    max_text: int,
    max_representatives: int,
) -> dict[str, object]:
    nodes: list[dict[str, object]] = []

    def callback(child_hwnd: int, _extra: object) -> bool:
        try:
            thread_id, pid = win32process.GetWindowThreadProcessId(child_hwnd)
            class_name = win32gui.GetClassName(child_hwnd)
            rect = _window_rect(child_hwnd)
            nodes.append(
                {
                    "depth": _child_depth(child_hwnd, hwnd),
                    "hwnd": child_hwnd,
                    "class_name": class_name,
                    "window_text": _bounded_text(
                        win32gui.GetWindowText(child_hwnd),
                        max_text,
                    ),
                    "thread_id": thread_id,
                    "owning_pid": pid,
                    "visible": bool(win32gui.IsWindowVisible(child_hwnd)),
                    "enabled": bool(win32gui.IsWindowEnabled(child_hwnd)),
                    "rect": rect,
                    "non_zero_rect": _has_non_zero_rect(rect),
                    "parent_hwnd": win32gui.GetParent(child_hwnd),
                    "parent_chain": _parent_chain(child_hwnd, hwnd),
                    "z_order_previous": win32gui.GetWindow(
                        child_hwnd, win32con.GW_HWNDPREV
                    ),
                    "z_order_next": win32gui.GetWindow(
                        child_hwnd, win32con.GW_HWNDNEXT
                    ),
                    "active_mdi_child": _active_mdi_child(child_hwnd, class_name),
                }
            )
        except Exception as error:
            nodes.append(
                {
                    "depth": None,
                    "hwnd": child_hwnd,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
        return True

    win32gui.EnumChildWindows(hwnd, callback, None)
    class_counts = Counter(
        str(node["class_name"])
        for node in nodes
        if "class_name" in node
    )
    class_frequency = [
        {"class_name": class_name, "count": count}
        for class_name, count in sorted(
            class_counts.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
    ]
    return {
        "total_count": len(nodes),
        "class_name_frequency": class_frequency,
        "classes_seen_once": sorted(
            class_name
            for class_name, count in class_counts.items()
            if count == 1
        ),
        "representative_nodes": nodes[:max_representatives],
        "representative_limit": max_representatives,
        "truncated": len(nodes) > max_representatives,
    }


def _signature_family(class_name: str) -> str | None:
    if class_name.startswith("_Ww") or class_name in _WRITER_SIGNATURE_CLASSES:
        return "writer"
    if class_name in _PDF_SIGNATURE_CLASSES:
        return "pdf"
    if class_name in _PRESENTATION_SIGNATURE_CLASSES:
        return "presentation"
    return None


def _matched_signature_nodes(
    nodes: list[dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    matched: dict[str, list[dict[str, object]]] = {
        "writer": [],
        "pdf": [],
        "presentation": [],
    }
    for node in nodes:
        class_name = node.get("class_name")
        if not isinstance(class_name, str):
            continue
        family = _signature_family(class_name)
        if family is not None:
            matched[family].append(node)
    return matched


def _focus_signature_families(
    hwnd_focus: int,
    root_hwnd: int,
) -> tuple[list[str], list[dict[str, object]]]:
    if not hwnd_focus:
        return [], []
    chain = _parent_chain(hwnd_focus, root_hwnd)
    families = sorted(
        {
            family
            for item in chain
            if isinstance(item.get("class_name"), str)
            for family in [_signature_family(str(item["class_name"]))]
            if family is not None
        }
    )
    return families, chain


def _strong_signature_diagnostics(
    nodes: list[dict[str, object]],
) -> dict[str, object]:
    visible_non_zero = [
        node
        for node in nodes
        if bool(node.get("visible")) and bool(node.get("non_zero_rect"))
    ]
    visible_classes = [
        str(node["class_name"])
        for node in visible_non_zero
        if isinstance(node.get("class_name"), str)
    ]
    writer_ww_classes = sorted(
        {
            class_name
            for class_name in visible_classes
            if class_name in {"_WwB", "_WwC", "_WwF", "_WwG"}
        }
    )
    writer_corroborating_classes = sorted(
        {
            class_name
            for class_name in visible_classes
            if class_name
            in {
                "bosa_sdm_Microsoft Office Word 11.0",
                "MsoCommandBar",
                "MsoCommandBarDock",
            }
        }
    )
    pdf_has_container = "KCefContainerWindow" in visible_classes
    pdf_render_classes = sorted(
        {
            class_name
            for class_name in visible_classes
            if class_name
            in {"CefBrowserWindow", "Chrome_RenderWidgetHostHWND"}
        }
    )
    return {
        "writer": {
            "strong": len(writer_ww_classes) >= 2,
            "ww_classes": writer_ww_classes,
            "corroborating_classes": writer_corroborating_classes,
        },
        "pdf": {
            "strong": pdf_has_container and bool(pdf_render_classes),
            "has_kcef_container": pdf_has_container,
            "render_classes": pdf_render_classes,
            "qt5qwindowicon_is_auxiliary_only": (
                "Qt5QWindowIcon" in visible_classes
            ),
        },
        "visible_non_zero_classes": sorted(set(visible_classes)),
    }


def _focus_arbitration(
    hwnd_focus: int,
    root_hwnd: int,
) -> dict[str, object]:
    chain = _parent_chain(hwnd_focus, root_hwnd) if hwnd_focus else []
    classes = [
        str(item["class_name"])
        for item in chain
        if isinstance(item.get("class_name"), str)
    ]
    belongs_to_root = any(bool(item.get("is_root")) for item in chain)
    writer_matches = sorted(
        {
            class_name
            for class_name in classes
            if class_name in {"_WwB", "_WwC", "_WwF", "_WwG"}
        }
    )
    pdf_matches = sorted(
        {
            class_name
            for class_name in classes
            if class_name
            in {
                "Chrome_RenderWidgetHostHWND",
                "CefBrowserWindow",
                "KCefContainerWindow",
            }
        }
    )
    family = None
    if belongs_to_root and bool(writer_matches) != bool(pdf_matches):
        family = "writer" if writer_matches else "pdf"
    return {
        "hwnd_focus": hwnd_focus,
        "belongs_to_foreground_root": belongs_to_root,
        "ancestry": chain,
        "ancestry_classes": classes,
        "writer_matches": writer_matches,
        "pdf_matches": pdf_matches,
        "resolved_family": family,
    }


def _unknown_classification(
    reason: str,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    return {
        "subtype": "WPS_UNKNOWN",
        "confidence": "UNKNOWN",
        "evidence": [reason],
        "diagnostics": {**diagnostics, "reason": reason},
    }


def classify_wps_hwnd(
    hwnd: int,
    child_tree: dict[str, object] | None = None,
    gui_thread_info: dict[str, object] | None = None,
) -> dict[str, object]:
    """Classify only strong WPS evidence; otherwise return WPS_UNKNOWN."""

    if not hwnd or not win32gui.IsWindow(hwnd):
        return _unknown_classification("invalid_hwnd", {})

    thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
    process_image, process_error = _query_process_image(pid)
    if not process_image or not process_image.casefold().endswith("\\wps.exe"):
        return _unknown_classification(
            "foreground_owner_is_not_wps_exe",
            {
                "owner_pid": pid,
                "owner_exe": process_image,
                "owner_exe_error": process_error,
            },
        )

    tree = child_tree or _collect_children(hwnd, 120, 256)
    gui_info = gui_thread_info or _query_gui_thread_info(thread_id)
    nodes = list(tree.get("representative_nodes", []))
    matched = _matched_signature_nodes(nodes)
    top_class = win32gui.GetClassName(hwnd)
    hwnd_focus = int(gui_info.get("hwndFocus", 0) or 0)
    strong = _strong_signature_diagnostics(nodes)
    focus = _focus_arbitration(hwnd_focus, hwnd)
    diagnostics = {
        "owner_pid": pid,
        "top_level_class": top_class,
        "child_tree_truncated": bool(tree.get("truncated")),
        "writer_strong_evidence": strong["writer"],
        "pdf_strong_evidence": strong["pdf"],
        "focus": focus,
    }

    presentation_classes = sorted(
        {
            str(node["class_name"])
            for node in matched["presentation"]
            if isinstance(node.get("class_name"), str)
        }
    )
    if top_class == "PP12FrameClass" and presentation_classes:
        diagnostics["presentation_signature_classes"] = presentation_classes
        return {
            "subtype": "WPS_PRESENTATION",
            "confidence": "HIGH",
            "evidence": [
                "top_level_class=PP12FrameClass",
                "presentation_child_signature="
                + ",".join(presentation_classes),
            ],
            "diagnostics": diagnostics,
        }

    if tree.get("truncated"):
        return _unknown_classification("child_tree_truncated", diagnostics)

    writer_strong = bool(strong["writer"]["strong"])
    pdf_strong = bool(strong["pdf"]["strong"])
    if writer_strong and not pdf_strong:
        return {
            "subtype": "WPS_WRITER",
            "confidence": "HIGH",
            "evidence": [
                "multiple_visible_non_zero_Ww_classes="
                + ",".join(strong["writer"]["ww_classes"])
            ],
            "diagnostics": diagnostics,
        }
    if pdf_strong and not writer_strong:
        return {
            "subtype": "WPS_PDF",
            "confidence": "HIGH",
            "evidence": [
                "visible_non_zero_KCefContainerWindow",
                "visible_non_zero_pdf_render_class="
                + ",".join(strong["pdf"]["render_classes"]),
            ],
            "diagnostics": diagnostics,
        }
    if not writer_strong and not pdf_strong:
        return _unknown_classification(
            "neither_writer_nor_pdf_has_strong_evidence",
            diagnostics,
        )

    focus_family = focus["resolved_family"]
    if focus_family == "writer":
        return {
            "subtype": "WPS_WRITER",
            "confidence": "HIGH",
            "evidence": [
                "writer_and_pdf_both_strong",
                "focus_ancestry_uniquely_matches_writer="
                + ",".join(focus["writer_matches"]),
            ],
            "diagnostics": diagnostics,
        }
    if focus_family == "pdf":
        return {
            "subtype": "WPS_PDF",
            "confidence": "HIGH",
            "evidence": [
                "writer_and_pdf_both_strong",
                "focus_ancestry_uniquely_matches_pdf="
                + ",".join(focus["pdf_matches"]),
            ],
            "diagnostics": diagnostics,
        }
    return _unknown_classification(
        "writer_and_pdf_both_strong_but_focus_is_unattributed_or_ambiguous",
        diagnostics,
    )


def _query_processes(owner_pid: int) -> dict[str, object]:
    try:
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        service = win32com.client.GetObject(
            "winmgmts:{impersonationLevel=impersonate}!\\\\.\\root\\cimv2"
        )
        raw_processes = list(
            service.ExecQuery(
                "SELECT ProcessId, ParentProcessId, Name, ExecutablePath, "
                "CommandLine FROM Win32_Process"
            )
        )
        all_processes: dict[int, dict[str, object]] = {}
        for process in raw_processes:
            pid = int(process.ProcessId)
            all_processes[pid] = {
                "pid": pid,
                "ppid": int(process.ParentProcessId or 0),
                "name": str(process.Name or ""),
                "exe": str(process.ExecutablePath or ""),
                "command_line": str(process.CommandLine or ""),
            }
        process = None
        raw_processes.clear()
        service = None
        gc.collect()

        def is_descendant(pid: int, ancestor_pid: int) -> bool:
            visited: set[int] = set()
            current = pid
            while current and current not in visited:
                visited.add(current)
                process = all_processes.get(current)
                if process is None:
                    return False
                parent = int(process["ppid"])
                if parent == ancestor_pid:
                    return True
                current = parent
            return False

        owner_parent = int(all_processes.get(owner_pid, {}).get("ppid", 0))
        wps_processes: list[dict[str, object]] = []
        for process in all_processes.values():
            name = str(process["name"]).casefold()
            executable_path = str(process["exe"]).casefold()
            if (
                name not in _WPS_PROCESS_NAMES
                and "kingsoft" not in executable_path
                and "wps office" not in executable_path
            ):
                continue

            pid = int(process["pid"])
            ppid = int(process["ppid"])
            if pid == owner_pid:
                relation = "foreground_owner"
            elif ppid == owner_pid:
                relation = "direct_child_of_foreground_owner"
            elif pid == owner_parent:
                relation = "direct_parent_of_foreground_owner"
            elif is_descendant(pid, owner_pid):
                relation = "descendant_of_foreground_owner"
            elif is_descendant(owner_pid, pid):
                relation = "ancestor_of_foreground_owner"
            else:
                relation = "other_wps_process"
            wps_processes.append({**process, "relation": relation})

        return {
            "status": "ok",
            "foreground_owner_pid": owner_pid,
            "items": sorted(
                wps_processes,
                key=lambda item: (str(item["relation"]), int(item["pid"])),
            ),
        }
    except Exception as error:
        return {
            "status": "unsupported_or_failed",
            "error": f"{type(error).__name__}: {error}",
            "foreground_owner_pid": owner_pid,
            "items": [],
        }
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def collect_snapshot(
    label: str,
    max_text: int,
    max_representatives: int,
) -> dict[str, Any]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("GetForegroundWindow returned no HWND")

    thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
    process_image, process_image_error = _query_process_image(pid)
    gui_thread_info = _query_gui_thread_info(thread_id)
    child_tree = _collect_children(
        hwnd,
        max_text=max_text,
        max_representatives=max_representatives,
    )
    classification = classify_wps_hwnd(
        hwnd,
        child_tree=child_tree,
        gui_thread_info=gui_thread_info,
    )
    return {
        "schema": "shortcut_hud_wps_identity_probe_v1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "foreground": {
            "hwnd": hwnd,
            "window_title": _bounded_text(
                win32gui.GetWindowText(hwnd),
                max_text,
            ),
            "top_level_class_name": win32gui.GetClassName(hwnd),
            "thread_id": thread_id,
            "owner_process_pid": pid,
            "owner_exe": process_image,
            "owner_exe_error": process_image_error,
        },
        "win32_metadata": {
            "style": _hex(win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)),
            "extended_style": _hex(
                win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ),
            "parent_hwnd": win32gui.GetParent(hwnd),
            "owner_hwnd": win32gui.GetWindow(hwnd, win32con.GW_OWNER),
            "thread_id": thread_id,
            "module_file_name": _query_window_module(hwnd),
        },
        "window_properties": _enum_window_properties(hwnd),
        "gui_thread_info": gui_thread_info,
        "classification": classification,
        "child_window_tree": child_tree,
        "wps_process_relationships": _query_processes(pid),
    }




def _write_snapshot(snapshot: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _snapshot_summary(snapshot: dict[str, Any]) -> dict[str, object]:
    classification = snapshot["classification"]
    diagnostics = classification.get("diagnostics", {})
    focus = diagnostics.get("focus", {})
    return {
        "label": snapshot["label"],
        "foreground": snapshot["foreground"],
        "candidate": classification["subtype"],
        "confidence": classification["confidence"],
        "evidence": classification["evidence"],
        "writer_strong_evidence": diagnostics.get(
            "writer_strong_evidence", {}
        ),
        "pdf_strong_evidence": diagnostics.get("pdf_strong_evidence", {}),
        "focus_hwnd": focus.get("hwnd_focus", 0),
        "focus_ancestry": focus.get("ancestry", []),
        "child_count": snapshot["child_window_tree"]["total_count"],
    }


def _current_classification_report() -> dict[str, object]:
    hwnd = int(win32gui.GetForegroundWindow() or 0)
    classification = classify_wps_hwnd(hwnd)
    diagnostics = classification.get("diagnostics", {})
    focus = diagnostics.get("focus", {})
    return {
        "HWND": hwnd,
        "top_class": (
            win32gui.GetClassName(hwnd)
            if hwnd and win32gui.IsWindow(hwnd)
            else None
        ),
        "writer_strong_evidence": diagnostics.get(
            "writer_strong_evidence", {}
        ),
        "pdf_strong_evidence": diagnostics.get("pdf_strong_evidence", {}),
        "focus_hwnd": focus.get("hwnd_focus", 0),
        "focus_ancestry": focus.get("ancestry", []),
        "classification": {
            "subtype": classification["subtype"],
            "confidence": classification["confidence"],
            "evidence": classification["evidence"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--classify", action="store_true")
    parser.add_argument("--label", default="snapshot")
    parser.add_argument("--max-text", type=int, default=120)
    parser.add_argument("--max-representatives", type=int, default=80)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.classify:
        print(
            json.dumps(
                _current_classification_report(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.output is None:
        raise RuntimeError("--output is required outside classify mode")
    snapshot = collect_snapshot(
        label=args.label,
        max_text=max(20, args.max_text),
        max_representatives=max(1, args.max_representatives),
    )
    _write_snapshot(snapshot, args.output)
    print(f"Snapshot written: {args.output.resolve()}")
    print(
        json.dumps(
            {
                **_snapshot_summary(snapshot),
                "property_status": snapshot["window_properties"]["status"],
                "wps_process_count": len(
                    snapshot["wps_process_relationships"]["items"]
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
