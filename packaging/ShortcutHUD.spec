# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the ShortcutHUD portable Windows bundle (onedir)."""

a = Analysis(
    ["../main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ShortcutHUD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="../assets/app_icon.ico",
    version="../packaging/version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ShortcutHUD",
)
