# ShortcutHUD

**ShortcutHUD** is a lightweight Windows shortcut-discovery HUD. Hold a modifier key (Ctrl, Shift, Alt, Win, or a combination) and a small, non-intrusive panel shows the high-value shortcuts for the current foreground application, together with relevant global shortcuts. Release all modifiers and the HUD disappears.

ShortcutHUD is based on [shortcut_overlay](https://github.com/ByronLeeeee/shortcut_overlay) by ByronLeeeee (MIT License) and continues it as a compact HUD instead of a full virtual keyboard.

[中文说明 (Chinese Version)](README_zh.md)

## Features

*   **Modifier-hold HUD**: hold Ctrl / Shift / Alt / Win to discover shortcuts; the same window updates in place as the combination changes.
*   **Application-aware**: detects the foreground application (Windows), including File Explorer, WPS Writer/PDF/Presentation, and shell surfaces.
*   **Built-in shortcut packs**: curated profiles for VS Code, Edge, Chrome, Office, Windows Terminal, Explorer, WPS, and more.
*   **Global shortcuts**: system-level shortcuts (Win, Alt+Tab, Ctrl+Shift+Esc) shown as a pinned global section for any app.
*   **Custom shortcut manager**: Settings → Shortcuts → Manage Shortcuts... lets you add per-app custom shortcuts with a recorder, hide or restore built-in app shortcuts, and set per-app display names. Data is stored in `%APPDATA%\ShortcutHUD\user_shortcuts.json`.
*   **Passive by design**: the HUD never takes focus, never swallows input, and never changes normal shortcuts.
*   **System tray**: runs quietly in the tray with settings, theme, opacity, and language options (English / 简体中文).

## Prerequisites

*   Windows 10/11
*   Python 3.10+ (3.13 tested)
*   PySide6
*   `keyboard`
*   `pywin32`
*   `comtypes`

## Installation & Setup

1.  **Clone this repository** and enter its directory.

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv .venv
    # On Windows
    .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python main.py
    ```

## Usage

*   Hold a modifier key over any application to see its shortcuts.
*   Manage your own shortcuts via the tray: **Settings... → Shortcuts → Manage Shortcuts...**.
*   Built-in shortcut data lives in `config/shortcuts.json`; your personal profiles live in `%APPDATA%\ShortcutHUD\user_shortcuts.json` and are never overwritten by the application itself.

## License

MIT License - see [LICENSE](LICENSE). Based on [shortcut_overlay](https://github.com/ByronLeeeee/shortcut_overlay) by ByronLeeeee. Icons by [Icons8](https://icons8.com).
