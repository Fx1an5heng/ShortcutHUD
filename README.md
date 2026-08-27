<p align="center">
  <img src="assets/app_icon.png" width="96" alt="ShortcutHUD icon" />
</p>

<h1 align="center">ShortcutHUD</h1>

<p align="center">Hold a modifier key and instantly discover the shortcuts that matter in the current app.</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue" alt="Windows 10/11" />
  <img src="https://img.shields.io/badge/Release-v0.5.0--beta.1-9cf" alt="Release v0.5.0-beta.1" />
  <img src="https://img.shields.io/badge/Status-Beta-orange" alt="Beta" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License" />
</p>

<p align="center">
  <a href="#quick-start">🚀 Quick Start</a> ·
  <a href="#how-it-works">💡 How It Works</a> ·
  <a href="#features">✨ Features</a> ·
  <a href="#supported-apps">📦 Supported Apps</a> ·
  <a href="#customization">✏️ Customization</a> ·
  <a href="#privacy--security">🛡 Privacy & Security</a> ·
  <a href="#faq">❓ FAQ</a> ·
  <a href="#roadmap">🗺 Roadmap</a> ·
  <a href="#development">🔧 Development</a> ·
  <a href="#license">📄 License</a>
</p>

---

## What is ShortcutHUD?

ShortcutHUD is a **shortcut discovery tool for Windows**: while you hold Ctrl, Shift, Alt, Win, or a combination, a small panel appears in the corner of the screen listing the shortcuts actually worth remembering for the current app. Release the keys and it disappears.

- ✅ Never steals focus from the app you are using
- ✅ Never swallows input — Ctrl+C / Ctrl+V / Alt+Tab keep working
- ✅ Only shows hints; it never replaces existing shortcuts
- ✅ Not a virtual keyboard — just a lightweight HUD

> The current Beta runs on Python; there is no exe installer yet (see [Roadmap](#roadmap)).
> Get the release or source: [GitHub Releases](https://github.com/Fx1an5heng/ShortcutHUD/releases)

---

## 🚀 Quick Start

> You only need to install Python once (see below). No Git, terminal, or venv knowledge required.

### Method A: Regular users (recommended for the current Beta)

1. **Install Python 3.10 or newer**
   Download it from <https://www.python.org/downloads/>.
   ⚠️ During installation, make sure to check **“Add Python to PATH”**.

2. **Download ShortcutHUD**
   On this repository page, click the green **Code** button → **Download ZIP**, then extract it anywhere.

3. **Double-click `start_shortcuthud.bat`**
   The first launch creates a local environment and downloads the required components (takes a few minutes, keep the internet connected). Later launches are much faster.

4. **A tray icon means it is running**
   Open VS Code, a browser, or any app, hold **Ctrl**, and the HUD appears.

### Method B: Developers

```bash
git clone https://github.com/Fx1an5heng/ShortcutHUD.git
cd ShortcutHUD
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

---

## 💡 How It Works

Open VS Code and hold **Ctrl**:

```
P   Quick Open
/   Toggle Comment
`   Terminal
B   Sidebar
```

Hold **Shift** as well: the same HUD updates in place to `Ctrl + Shift`. Release everything: it disappears.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🎯 App-aware | Detects the foreground application automatically |
| ⌨️ Shortcut HUD | Appears while holding modifiers; updates in place for combinations |
| 🌐 Global hints | Windows system shortcuts (Win, Alt+Tab, Ctrl+Shift+Esc) always pinned |
| ✏️ Customization | Add your own shortcuts and display names for any app |
| ⏺ Recorder | Click “Record Shortcut” and simply press the combination |
| 🙈 Hide built-ins | Hide built-in hints you don't want, restore them anytime |
| 🇨🇳 Bilingual UI | English / 简体中文 |
| 🛡 Passive by design | No focus stealing, no input swallowing |

---

## 📦 Supported Apps

Curated built-in shortcut packs: VS Code, Chrome, Edge, File Explorer, Windows Terminal, Word, Excel, PowerPoint, WPS Writer / PDF / Presentation, and more.

Apps without a built-in pack still work: global (GLOBAL) and default (DEFAULT) shortcuts are shown, and you can add your own custom profile for them.

---

## ✏️ Customization

Entry point: **system tray → Settings → Shortcuts → Manage Shortcuts...**

You can: add the current app, add/edit shortcuts (with recording), edit descriptions, hide built-in shortcuts, restore hidden items, and set per-app display names.

Power users: personal configuration lives in `%APPDATA%\ShortcutHUD\user_shortcuts.json` and is never overwritten by the application.

---

## 🛡 Privacy & Security

- All shortcut configuration stays **on your machine** (`%APPDATA%\ShortcutHUD\user_shortcuts.json`)
- The code contains **no network calls and no telemetry** (nothing is uploaded)
- Recording only captures local key events while you explicitly press “Record Shortcut”; **no input history is stored**

---

## ❓ FAQ

**Q: I held Ctrl but no HUD appeared.**
A: ① Check that the current combination has entries; ② desktop/taskbar surfaces only show global shortcuts by default; ③ make sure ShortcutHUD is running in the tray.

**Q: Why is the first launch slow?**
A: The first run downloads the Python components; later runs are fast.

**Q: Why does an app show no shortcuts?**
A: It has no built-in pack yet. Add your own via “Manage Shortcuts...”; global shortcuts always apply.

**Q: How do I add my own shortcuts?**
A: Tray → Settings → Shortcuts → Manage Shortcuts... → Add Current App → Add / Record.

**Q: Why doesn't the Recorder record Win+R?**
A: The Beta recorder only auto-records single-step shortcuts with Ctrl / Alt / Shift. Win and system-reserved combinations (e.g. Alt+F4, Ctrl+Shift+Esc) must be entered manually.

**Q: How do I fully exit ShortcutHUD?**
A: Right-click the tray icon → Exit.

**Q: Where is my configuration stored?**
A: `%APPDATA%\ShortcutHUD\user_shortcuts.json`.

---

## ⚠️ Known Limitations (Beta)

- Chord / sequence shortcuts (e.g. `Ctrl+K Ctrl+S`) are not supported yet
- Win / system-reserved combinations are manual-entry only in the Recorder
- Automatic Vim / Neovim context detection inside terminals is still experimental
- Custom language packs are not implemented yet

---

## 🗺 Roadmap

- **Portable EXE / Installer** (next — remove the Python requirement for regular users)
- Chord / sequence shortcuts
- Richer application & context detection
- Custom language packs
- Additional shortcut packs

---

## 🔧 Development

Requirements: Windows 10/11, Python 3.10+ (3.13 tested), PySide6, `keyboard`, `pywin32`, `comtypes`.

```bash
git clone https://github.com/Fx1an5heng/ShortcutHUD.git
cd ShortcutHUD
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -B -m unittest discover -s tests
```

Engineering conventions live in [AGENTS.md](AGENTS.md).

---

## 📄 License

[MIT](LICENSE). Based on [ByronLeeeee/shortcut_overlay](https://github.com/ByronLeeeee/shortcut_overlay) (MIT). Icons by [Icons8](https://icons8.com).
