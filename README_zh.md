# ShortcutHUD

**ShortcutHUD** 是一款轻量的 Windows 快捷键发现 HUD。按住修饰键（Ctrl、Shift、Alt、Win 或其组合），屏幕角落会出现一个小巧、不打扰的悬浮面板，显示当前前台应用的高价值快捷键以及相关的全局快捷键。松开所有修饰键后 HUD 立即消失。

ShortcutHUD 基于 ByronLeeeee 的 [shortcut_overlay](https://github.com/ByronLeeeee/shortcut_overlay)（MIT 协议）继续开发，并将其从完整虚拟键盘改造为紧凑的快捷键 HUD。

[English Version (英文说明)](README.md)

## 功能特性

*   **按住修饰键显示 HUD**: 按住 Ctrl / Shift / Alt / Win 即可发现快捷键；组合变化时同一窗口原位更新。
*   **应用感知**: 自动识别前台应用（Windows），包括文件资源管理器、WPS 文字/PDF/演示以及桌面/任务栏等系统界面。
*   **内置快捷键包**: 为 VS Code、Edge、Chrome、Office、Windows Terminal、资源管理器、WPS 等应用精选的快捷键配置。
*   **全局快捷键**: Win、Alt+Tab、Ctrl+Shift+Esc 等系统级快捷键作为固定全局区显示，适用于任何应用。
*   **自定义快捷键管理器**: 设置 → 快捷键 → 管理快捷键... 可为任意应用添加自定义快捷键（支持录制）、隐藏或恢复应用内置快捷键、设置显示名称。数据保存在 `%APPDATA%\ShortcutHUD\user_shortcuts.json`。
*   **纯被动设计**: HUD 不抢焦点、不吞按键、不改变任何正常快捷键。
*   **系统托盘**: 常驻托盘，提供设置、主题、透明度与语言（英文 / 简体中文）选项。

## 系统需求

*   Windows 10/11
*   Python 3.10+（已测试 3.13）
*   PySide6
*   `keyboard`
*   `pywin32`
*   `comtypes`

## 安装与设置

1.  **克隆本仓库**并进入目录。

2.  **创建并激活虚拟环境（推荐）:**
    ```bash
    python -m venv .venv
    # Windows 系统
    .venv\Scripts\activate
    ```

3.  **安装依赖:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **运行应用程序:**
    ```bash
    python main.py
    ```

## 使用说明

*   在任意应用上按住修饰键即可查看其快捷键。
*   通过托盘管理自己的快捷键：**设置... → 快捷键 → 管理快捷键...**。
*   内置快捷键数据位于 `config/shortcuts.json`；个人配置位于 `%APPDATA%\ShortcutHUD\user_shortcuts.json`，应用本身绝不会覆盖它。

## 许可证

MIT 协议 - 详见 [LICENSE](LICENSE)。基于 ByronLeeeee 的 [shortcut_overlay](https://github.com/ByronLeeeee/shortcut_overlay) 开发。图标来自 [Icons8](https://icons8.com)。
