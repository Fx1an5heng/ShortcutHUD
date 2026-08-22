"""Read the focused WPS UI Automation ancestry through Python/comtypes.

This is a read-only Phase 4B gate. It does not import production modules or
perform UI Automation actions.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import statistics
import time

import comtypes
import comtypes.client


MAX_DEPTH = 40


def _classify(classes: list[str], reached_root: bool) -> str:
    if not reached_root:
        return "WPS_UNKNOWN"

    families: set[str] = set()
    class_set = set(classes)
    if "KxWpsView" in class_set and (
        "KxWpsDocPane" in class_set or "KxWpsMainWindow" in class_set
    ):
        families.add("WPS_WRITER")
    if {
        "KxPdfView",
        "KxPdfDocPane",
        "KxPdfMainWindow",
    }.issubset(class_set):
        families.add("WPS_PDF")
    if "KxWppView" in class_set and (
        "KxWppSlidePane" in class_set or "KxWppMainWindow" in class_set
    ):
        families.add("WPS_PRESENTATION")
    if len(families) == 1:
        return next(iter(families))
    return "WPS_UNKNOWN"


def _sample(automation: object, uia: object) -> dict[str, object]:
    hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    root = automation.ElementFromHandle(hwnd)
    focused = automation.GetFocusedElement()
    walker = automation.ControlViewWalker

    classes: list[str] = []
    reached_root = False
    current = focused
    for _ in range(MAX_DEPTH):
        if not current:
            break
        classes.append(str(current.CurrentClassName or ""))
        if automation.CompareElements(current, root):
            reached_root = True
            break
        current = walker.GetParentElement(current)

    return {
        "hwnd": hwnd,
        "root_class": str(root.CurrentClassName or ""),
        "focused_class": str(focused.CurrentClassName or ""),
        "control_ancestry_classes": classes,
        "reached_foreground_root": reached_root,
        "classification": _classify(classes, reached_root),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=int, default=0)
    args = parser.parse_args()

    uia = comtypes.client.GetModule("UIAutomationCore.dll")
    automation = comtypes.client.CreateObject(
        uia.CUIAutomation,
        interface=uia.IUIAutomation,
    )

    result = _sample(automation, uia)
    result["python"] = __import__("sys").version.split()[0]
    result["comtypes"] = comtypes.__version__

    if args.benchmark > 0:
        timings: list[float] = []
        classifications: dict[str, int] = {}
        for _ in range(args.benchmark):
            started = time.perf_counter()
            sample = _sample(automation, uia)
            timings.append((time.perf_counter() - started) * 1000)
            classification = str(sample["classification"])
            classifications[classification] = classifications.get(classification, 0) + 1
        ordered = sorted(timings)
        p95_index = max(0, int(0.95 * len(ordered) + 0.999999) - 1)
        result["benchmark"] = {
            "iterations": len(ordered),
            "median_ms": statistics.median(ordered),
            "p95_ms": ordered[p95_index],
            "max_ms": ordered[-1],
            "classifications": classifications,
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
