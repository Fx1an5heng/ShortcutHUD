<p align="center">
  <img src="assets/app_icon.png" width="96" alt="ShortcutHUD icon" />
</p>

<h1 align="center">ShortcutHUD</h1>

<p align="center">按住修饰键，即刻发现当前应用的高价值快捷键。</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue" alt="Windows 10/11" />
  <img src="https://img.shields.io/badge/Release-v0.5.0--beta.2-9cf" alt="Release v0.5.0-beta.2" />
  <img src="https://img.shields.io/badge/Status-Beta-orange" alt="Beta" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License" />
</p>

<p align="center">
  <a href="https://github.com/Fx1an5heng/ShortcutHUD/releases/download/v0.5.0-beta.2/ShortcutHUD-v0.5.0-beta.2-win64.zip">⬇️ <b>Download for Windows</b></a>
  ·
  <a href="https://github.com/Fx1an5heng/ShortcutHUD/releases">Releases</a>
</p>

<p align="center">
  <a href="#1-分钟上手">🚀 1 分钟上手</a> ·
  <a href="#5-秒看懂怎么用">💡 5 秒看懂</a> ·
  <a href="#功能">✨ 功能</a> ·
  <a href="#支持的应用">📦 支持的应用</a> ·
  <a href="#自定义快捷键">✏️ 自定义</a> ·
  <a href="#隐私与安全">🛡 隐私与安全</a> ·
  <a href="#faq">❓ FAQ</a> ·
  <a href="#roadmap">🗺 Roadmap</a> ·
  <a href="#开发">🔧 开发</a> ·
  <a href="#license">📄 License</a>
</p>

---

## ShortcutHUD 是什么？

ShortcutHUD 是一个 **Windows 快捷键提示工具**：在你按住 Ctrl、Shift、Alt、Win 或其组合时，屏幕角落会显示一个小面板，列出**当前应用真正值得记住的快捷键**。松开按键，面板立即消失。

- ✅ 不抢焦点，不影响你正在使用的软件
- ✅ 不吞按键，Ctrl+C / Ctrl+V / Alt+Tab 一切照常
- ✅ 只做提示，不代替任何原有快捷键
- ✅ 不是虚拟键盘，只是一个轻量 HUD

> ⬇️ 普通用户直接下载便携版即可，**不需要安装 Python**：[Download for Windows](https://github.com/Fx1an5heng/ShortcutHUD/releases/download/v0.5.0-beta.2/ShortcutHUD-v0.5.0-beta.2-win64.zip)
>
> 便携版运行不需要联网。当前 exe 尚未做商业代码签名，Windows 可能显示 SmartScreen “Unknown publisher” 类提示；如果下载来源确认是本仓库的 GitHub Releases，可核对页面上的 SHA256 校验值。不要关闭 Defender 或 SmartScreen。

---

## 🚀 1 分钟上手

### 方法 A：下载 Windows 便携版（推荐）

不需要 Python、Git、pip、虚拟环境或命令行。

1. **点击 [Download for Windows](https://github.com/Fx1an5heng/ShortcutHUD/releases/download/v0.5.0-beta.2/ShortcutHUD-v0.5.0-beta.2-win64.zip)**
2. 下载 `ShortcutHUD-v0.5.0-beta.2-win64.zip`
3. 解压 ZIP
4. 双击 **`ShortcutHUD.exe`**
5. 系统托盘出现 ShortcutHUD 图标
6. 打开 VS Code / Chrome 等程序
7. 按住 **Ctrl**
8. HUD 出现

### 方法 B：从源码运行

适合开发者、想运行最新源码或自行修改 ShortcutHUD 的人。

1. **安装 Python 3.10 或更高版本**
   从 <https://www.python.org/downloads/> 下载安装。
   ⚠️ 安装时务必勾选 **“Add Python to PATH”**。

2. **下载源码**
   打开本仓库页面，点击绿色 **Code** 按钮 → **Download ZIP**，然后解压到任意位置。

3. **双击 `start_shortcuthud.bat`**
   第一次启动会自动创建环境并联网下载组件（需要几分钟，请保持联网）；以后启动会快很多。

4. **看到托盘图标即成功**
   打开 VS Code、浏览器等应用，按住 **Ctrl**，HUD 就会出现。

---

## 💡 5 秒看懂怎么用

打开 VS Code，按住 **Ctrl**：

```
P   Quick Open
/   Toggle Comment
`   Terminal
B   Sidebar
```

再按住 **Shift**：HUD 原位更新为 `Ctrl + Shift` 的快捷键。全部松开：HUD 消失。

---

## ✨ 功能

| 功能 | 说明 |
|---|---|
| 🎯 应用感知 | 自动识别当前前台应用并显示对应快捷键 |
| ⌨️ 快捷键 HUD | 按住修饰键即时显示，组合变化原位更新 |
| 🌐 全局提示 | Win、Alt+Tab、Ctrl+Shift+Esc 等系统快捷键固定展示 |
| ✏️ 自定义 | 为任意应用添加自己的快捷键与显示名称 |
| ⏺ 快捷键录制 | 点一下“录制快捷键”，直接按下组合即可录入 |
| 🙈 隐藏内置 | 不想看到的内置提示可以隐藏，随时恢复 |
| 🇨🇳 中英双语 | English / 简体中文 界面 |
| 🛡 被动设计 | 不抢焦点、不吞按键、不改变任何正常快捷键 |

---

## 📦 支持的应用

内置精选快捷键包：VS Code、Chrome、Edge、文件资源管理器、Windows Terminal、Word、Excel、PowerPoint、WPS 文字 / PDF / 演示，以及其它常见软件。

未内置的应用也能用：可显示全局（GLOBAL）与默认（DEFAULT）快捷键，也可以为它添加你自己的自定义 profile。

---

## ✏️ 自定义快捷键

入口：**系统托盘 → 设置 → 快捷键 → 管理快捷键...**

可以：添加当前应用、添加/编辑快捷键（支持录制）、修改描述、隐藏内置快捷键、恢复隐藏项、设置应用显示名称。

高级用户：个人配置保存在 `%APPDATA%\ShortcutHUD\user_shortcuts.json`，应用本身永远不会覆盖它。

---

## 🛡 隐私与安全

- 快捷键配置全部保存在**本机**（`%APPDATA%\ShortcutHUD\user_shortcuts.json`）
- 代码中**没有任何网络通信或遥测**（无上传逻辑）
- 快捷键录制仅在点击“录制快捷键”后、在设置窗口内短暂生效；**不保存任何输入历史**
- **便携版运行本身不需要联网**；只有“从源码运行”首次安装依赖时才需要 pip 联网
- 当前 exe 未做商业代码签名，Windows 可能显示 SmartScreen 提示；请仅从本仓库的 GitHub Releases 下载，并可核对 SHA256 校验值（不要关闭 Defender / SmartScreen）

---

## ❓ FAQ

**Q：按住 Ctrl 为什么没有 HUD？**
A：① 确认当前组合下确实有快捷键条目；② 桌面/任务栏等系统界面默认只显示全局快捷键；③ 确认 ShortcutHUD 已在托盘运行。

**Q：源码方式第一次运行为什么很慢？**
A：首次启动需要联网下载 Python 组件；之后就快了。（便携版没有这一步。）

**Q：为什么某个软件没有快捷键？**
A：该软件暂未内置快捷键包。你可以用“管理快捷键”为它添加自定义快捷键；全局快捷键始终可用。

**Q：怎么添加自己的快捷键？**
A：托盘 → 设置 → 快捷键 → 管理快捷键... → 添加当前应用 → 添加 / 录制。

**Q：为什么 Recorder 不录 Win+R？**
A：Beta 版录制器只自动录制包含 Ctrl / Alt / Shift 的单步快捷键；Win 组合与系统保留组合（如 Alt+F4、Ctrl+Shift+Esc）请手动输入。

**Q：怎么彻底退出 ShortcutHUD？**
A：右键托盘图标 → 退出（Exit）。

**Q：我的配置放在哪里？**
A：`%APPDATA%\ShortcutHUD\user_shortcuts.json`。

---

## ⚠️ Known Limitations（Beta）

- 多段 / chord 快捷键（如 `Ctrl+K Ctrl+S`）尚未支持
- Recorder 对 Win / 系统保留组合需手工输入
- 终端内 Vim / Neovim 的上下文自动识别仍不成熟
- 自定义语言包尚未实现
- 尚无 Installer / onefile 单文件版（当前为便携 ZIP）

---

## 🗺 Roadmap

- **Installer**（下一步，进一步简化安装）
- chord / 多段快捷键
- 更丰富的应用与上下文识别
- 自定义语言包
- 更多内置快捷键包

---

## 🔧 开发

环境要求：Windows 10/11、Python 3.10+（已测试 3.13）、PySide6、`keyboard`、`pywin32`、`comtypes`。

```bash
git clone https://github.com/Fx1an5heng/ShortcutHUD.git
cd ShortcutHUD
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -B -m unittest discover -s tests
```

本仓库的工程约定见 [AGENTS.md](AGENTS.md)。

---

## 📄 License

[MIT](LICENSE)。基于 [ByronLeeeee/shortcut_overlay](https://github.com/ByronLeeeee/shortcut_overlay)（MIT）开发。图标来自 [Icons8](https://icons8.com)。
