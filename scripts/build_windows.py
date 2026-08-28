"""Build the ShortcutHUD portable Windows bundle with PyInstaller (onedir).

One command: clean old outputs -> PyInstaller build -> copy bundled
read-only resources next to the exe -> validate the final directory.

Run from the repository root:

    .\.venv\Scripts\python.exe scripts\build_windows.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "ShortcutHUD"
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

REQUIRED_FILES = (
    "ShortcutHUD.exe",
    "config/shortcuts.json",
    "config/settings.json",
    "assets/app_icon.ico",
    "i18n/shortcut_overlay_zh_CN.qm",
)


def run(args: list[str]) -> None:
    subprocess.run([str(VENV_PYTHON), *args], cwd=ROOT, check=True)


def main() -> int:
    for path in (ROOT / "build", ROOT / "dist"):
        shutil.rmtree(path, ignore_errors=True)

    run(["-m", "PyInstaller", "--noconfirm", "--clean", "packaging/ShortcutHUD.spec"])

    if not (DIST / "ShortcutHUD.exe").exists():
        print("ERROR: ShortcutHUD.exe was not produced", file=sys.stderr)
        return 1

    # Bundled read-only defaults live next to the exe so portable copies work.
    for name in ("config", "assets", "i18n"):
        source = ROOT / name
        target = DIST / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)

    for relative in REQUIRED_FILES:
        if not (DIST / relative).exists():
            print(f"ERROR: missing required file: {relative}", file=sys.stderr)
            return 1

    files = [path for path in DIST.rglob("*") if path.is_file()]
    size_bytes = sum(path.stat().st_size for path in files)
    print(f"BUILD OK: {DIST}")
    print(f"  files: {len(files)}")
    print(f"  size: {size_bytes / 1024 / 1024:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
