@echo off
setlocal EnableExtensions
rem ShortcutHUD one-click launcher for first-time users.
rem Requirements: Python 3.10+ installed with "Add Python to PATH" checked.
rem This script never runs as administrator, never touches the global
rem Python installation, and installs only this project's requirements.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ShortcutHUD] Python was not found on this computer.
    echo Please install Python 3.10 or newer from:
    echo     https://www.python.org/downloads/
    echo During installation, remember to check Add Python to PATH.
    echo Then double-click this file again.
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [ShortcutHUD] First run - creating a local environment, please wait...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ShortcutHUD] Failed to create the local environment.
        echo.
        pause
        exit /b 1
    )
)

if not exist ".venv\.requirements-installed" (
    echo [ShortcutHUD] First run - downloading required components, needs internet...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ShortcutHUD] Failed to download components. Please check your
        echo internet connection and try again.
        echo.
        pause
        exit /b 1
    )
    type nul > ".venv\.requirements-installed"
)

echo [ShortcutHUD] Starting... - later runs start faster
".venv\Scripts\python.exe" main.py

echo.
echo [ShortcutHUD] ShortcutHUD has exited.
pause
endlocal
