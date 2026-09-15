# KeyPath v1：Full Guide 内的只读路径导航

状态：Accepted，2026-09-15。

## 问题

Full Guide 已经能按快捷键、描述和 modifier 查询，但用户只知道“想打开终端”时，仍要先猜搜索词或浏览上百条记录。我们需要一种从功能分类逐步缩小范围的键盘交互，同时不能把 ShortcutHUD 变成命令执行器，也不能复制一套 Catalog、前台应用或输入状态系统。

## 决策

KeyPath 是一个 Full Guide session 内的显式模式：

```text
GuideMode.NORMAL
  └─ Tab / 点击“路径导航”
      GuideMode.KEYPATH / ROOT
        └─ category hint → CATEGORY
             └─ action hint → RESULT
```

它不是顶层窗口、应用状态或新入口。再次触发 Full Guide 全局快捷键仍关闭整个 Guide。Esc 从 ROOT、CATEGORY 或 RESULT 一次回到 NORMAL；Backspace 只负责 RESULT → CATEGORY → ROOT，ROOT 下无操作。

## 数据边界

Controller 在进入 KeyPath 的瞬间读取 `FullGuideWindow.sections`。这批 section 已经过：

```text
open-time application snapshot
→ Catalog resolved/dedup presentation
→ cumulative modifier filter
→ text query
→ visible category sections
→ KeyPath dataset
```

因此 KeyPath 自然继承 USER_APP > APP > DEFAULT > GLOBAL、完整 trigger、隐藏规则与 presentation dedup，不重读 Pack、不重新读取 foreground、不做 Quick HUD eligibility 过滤。进入后的 dataset 固定到本次路径导航；返回 NORMAL 时原 query、modifier filter、滚动位置和 search focus 都保留。

## Hint 分配

`KeyPathHintAllocator` 是纯逻辑。每层输入为 stable identity、可选 preferred mnemonic、英文语义来源与 aliases；输出只包含 ASCII 字母或数字，不使用中文展示文本首字母，也不依赖 set/hash/widget 顺序。

分类可为核心 stable category key 声明稳定 mnemonic，例如 `integrated_terminal → T`、`navigation → N`、`search → S`。动作依次从显式 hint、English title/description、aliases、stable identity 提取有意义的字符，再使用固定 A-Z/0-9 fallback。分配按 stable identity 排序，所以输入数组顺序变化不改变结果。

同层不超过 36 项时全部使用唯一单字符。超过 36 项时，同层整体切到足够长度的固定宽度 base-36 hint；不会混用 `A` 与 `A1`，因此没有前缀不可达问题，数量继续增长也不会 crash。不同层是独立 scope，可以合法复用同一字符，所以终端路径可以是 `T → T`。

## 输入所有权

NORMAL 沿用既有文字搜索和 modifier tap filter。KEYPATH 时搜索框 disabled 且失去焦点，窗口消费字母、数字、Backspace 以及 modifier Qt 事件；Controller 同时忽略来自 Guide Win input service 的 modifier 事件，原 filter 不会漂移。鼠标点击 category/action 发送相同的导航 intent。

Guide active/focused/foreground 的现有 Win session ownership 不变：Win 与 Win chord 仍由原 `GuideWinInputService` 接管，退出整个 Guide 后立即恢复。Quick HUD 从 Guide 打开到关闭持续 suspended。没有改 KeyboardHandler、AltGr、WinDiscoveryProxy、activation hotkey 或 suppression policy。

RESULT 只展示 localized action label、完整 shortcut trigger 与 hint path。它不发送键盘事件、不调用应用 command、不执行 automation。

## 性能

Hint 和 KeyPath dataset 只在显式进入时从当前内存 section 构造一次。切层只操作小型 tuple 并重绘当前面板；没有磁盘、网络、后台线程或 polling。离开模式后不保留定时工作。

## 后果与后续边界

- Full Guide 窗口新增一个轻量内嵌 presentation panel，但 Catalog resolution 仍只有一套。
- KeyPath 的 category/action hints 是导航身份，不参与搜索、快捷键 identity 或 selection persistence。
- v1 明确不包含 shortcut 执行、Hover Demo、Learning、quiz/bookmark、Developer Navigator 或 Command Center。
- 未来 RESULT 可以接只读 demo preview，但必须保持“展示结果”与“执行命令”分离。

