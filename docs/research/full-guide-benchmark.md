# Full Guide v1：交互调研

调研日期：2026-09-11，收尾复核：2026-09-12。依据官方文档、维护者主页与历史资料；没有运行 macOS 产品，没有复制第三方源码。

## 对照与取舍

| 产品 | 有证据的交互 | 本阶段采用 | 不采用 / 未确认 |
| --- | --- | --- | --- |
| KeyClu | 跟随当前应用、可调整布局、搜索与高亮、手工快捷键、收藏和隐藏 | 当前应用优先；分类而非管理表格；可调列数；用户条目轻量标识 | 不做收藏、学习或常驻面板；不照搬双击并按住 Cmd 的触发方式 |
| legacy CheatSheet | 按住 Cmd 查看当前应用快捷键的历史用法 | 少一个应用选择步骤，让用户直接读当前软件 | 原官网未能取得可用内容；不把搜索、退出细节、现代多屏表现写成已验证事实 |
| 当前 PowerToys Shortcut Guide | 前台应用与匹配的后台 manifest；分类；搜索；Ctrl+F；Esc 先清搜索再关闭；热键再次关闭 | 独立显式唤起；搜索和退出的一致行为 | 不做应用侧栏、后台应用扫描、置顶收藏或另一份推荐列表 |

KeyClu 维护者主页明确列出 Filter & Highlight、Adjustable View、Own Shortcuts 和菜单数据的覆盖限制。它不是任意软件所有快捷键的可靠自动发现器。[维护者主页](https://sergii.tatarenkov.name/apps/keyclu/)

其 README 明确列出可折叠组、收藏、隐藏和默认触发；CLI 文档提供列数及面板切换参数。本次没有验证 KeyClu 的 Esc、焦点或多屏回退时序，不能据此宣称 ShortcutHUD 已获得这些能力。[README](https://github.com/Anze/KeyCluCask)、[CLI 参数](https://github.com/Anze/KeyCluCask/wiki/Integrations-%E2%80%90-CLI-params)

CheatSheet 的参考限于当年的使用记录。由“当前应用 + 一次唤起”的流程推导出少导航、可扫读的设计方向，是本项目的设计判断，不是对其当前版本能力的测评。[DEVONtechnologies 历史文章](https://www.devontechnologies.com/blog/20190708-shortcuts)

PowerToys 文档现已描述应用级 searchable Guide，不能再按旧版“只显示 Windows 键提示”的印象设计。文档确认其用户交互；ShortcutHUD 的抢焦点前快照是我们自己的实现要求，并非声称审计过它的内部实现。[Microsoft Learn](https://learn.microsoft.com/en-us/windows/powertoys/shortcut-guide)

## ShortcutHUD 的区别

- Quick HUD 保持无焦点、8 条上限的被动提示；Full Guide 是显式打开的只读查询；Shortcut Center 才是编辑与跨应用浏览入口。
- 已审计的本地 Catalog、USER_APP 与 GLOBAL 构成内容，不读取菜单、扫描后台应用或依赖 PowerToys 运行。
- 复用现有中英文 Catalog 文本与 Application Registry。覆盖数写“已收录”，不承诺完整。
- 推荐只在原分类内显示星标并略靠前，不生成第二份条目；个人 Quick HUD 选择不是 Guide 的数据来源。

## 实现依据与许可证边界

Windows 的独立显式命令使用 RegisterHotKey。它报告注册失败，MOD_NOREPEAT 阻止长按重复；无 HWND 时消息进入注册线程。F12 和 Windows 键组合的保留规则需要主动尊重。[Win32 文档](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)

Qt 原生事件过滤器支持 Windows dispatcher 消息；窗口失活有独立事件，可与快捷键及关闭事件一起完成生命周期收口。[QAbstractNativeEventFilter](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractNativeEventFilter.html)、[QEvent](https://doc.qt.io/qt-6/qevent.html)

KeyClu 主项目标注 BSD-3-Clause-Clear，不应与其另一个扩展仓库的许可证混为一谈。本阶段仅借鉴交互原则，没有复制实现；项目原有 upstream MIT 声明保持不动。
