# 2026-09：KeyPath v1

## 从“能搜”到“能沿功能找到”

Full Guide 的第一版解决了完整 Catalog 的浏览与搜索，但它仍假设用户至少知道快捷键、命令名或搜索词。KeyPath 解决的是另一种真实情境：用户知道功能属于“集成终端”或“导航”，却记不起命令名和按键。它把当前可见 Guide 结果投影成 category → action → revealed shortcut，两次输入就能定位，同时刻意不执行最终快捷键。

研究 which-key 与 Office KeyTips 后，最值得保留的不是外观，而是 scoped hint：每一层只解释下一次输入，category 和 action 可以分别使用自己的 mnemonic 空间；Backspace 表示回到上层，Esc 表示退出当前模式。ShortcutHUD 又有自己的硬边界——Guide 已经拥有 query、modifier、前台 snapshot、dedup 和 Win 输入生命周期，所以 KeyPath 不能另起 resolver 或顶层窗口。

## 真正危险的是输入归属

最容易写出的版本只是把 KeyPath panel 显示出来，但 search box 仍持有焦点。这样字母可能进入搜索，modifier 也可能继续改变 Guide filter，用户无法判断自己到底在操作哪套状态。实现把模式放到 Controller，进入时重置未完成的 modifier tap、禁用 search，并让 Full Guide 窗口消费 KeyPath 的字母/数字/Backspace。Controller 在该模式下也忽略现有 Qt/Win modifier 通知，形成双层保护；Esc 则走既有 Guide shortcut，直接退出 KeyPath。

鼠标项主动设置为不可获取键盘焦点，点击 category/action 后输入仍归 Full Guide。退出时恢复进入前的 query、filter、整体滚动位置与 search focus，而不是重新解析或重开窗口。再次触发全局 Guide hotkey 仍经过原 `toggle()` 关闭整个 session，因此不会产生一个“Guide 已关、KeyPath 仍活着”的旁路状态。

## Hint 不能依赖中文，也不能只解决今天的 35 条

分类 hint 从 stable category key 和审校过的 preferred mnemonic 得到；动作 hint 从 English title/description、aliases、stable ID 中提取。中文只负责展示，切换 locale 不会让操作路径漂移。中文-only USER_APP 条目仍会得到数字或其它固定 fallback，不会因没有英文名消失。

碰撞处理必须同时满足确定性和可达性。<=36 项可以逐个找未占用的 A-Z/0-9；若第 37 项简单变成 `A1`，已有单字符 `A` 会提前提交，`A1` 永远无法选中。最终策略是在溢出时把整个 scope 一起切到固定宽度 base-36，必要时继续增加宽度。这样放弃了溢出层的单键速度，但结果唯一、无前缀冲突、顺序变化可重复，也不会因未来大 Pack 崩溃。

## 复用已解析视图，而不是再建 Catalog 支路

进入 KeyPath 时唯一的数据入口是窗口当前 `sections`。因此 `Ctrl filter + terminal query + Tab` 只得到当前屏幕已经可见的结果；USER_APP、APP、GLOBAL 的优先级、同 trigger 冲突和语义去重均由现有 Catalog presentation 链路提前完成。F5、Ctrl+K Ctrl+S、double-tap 等不适合 Quick HUD 的条目仍自然存在，因为 KeyPath 属于 Full Guide，不读取 Quick HUD selection，也不以 HUD eligibility 裁剪。

这也保持了应用快照语义：Guide 打开后成为前台不影响 KeyPath，因为它绝不重新查询 foreground。所有计算都在内存完成，进入时分配一次 hint，之后仅切换 session tuple 和 Qt presentation；没有 Pack 重读、磁盘扫描、网络或 idle polling。

## 验证重点

纯逻辑测试覆盖 preferred mnemonic、碰撞、输入顺序稳定性、中文-only fallback、36 项以上固定宽度、ROOT/CATEGORY/RESULT 与 Backspace，以及 single/combo/sequence/double_tap、USER_APP、GLOBAL 和 resolver precedence/dedup。

Qt/Controller 测试覆盖 Tab 与鼠标入口、三层键盘/鼠标导航、任意层 Esc 一次退出、全局 hotkey 关闭整个 Guide、filter/query 构成 KeyPath dataset、状态/滚动/焦点恢复、KeyPath 字母不写 search、modifier 不改变原 filter、空数据友好状态、结果 trigger 大字展示、无横向滚动和 zh_CN/en shell。完整回归继续负责 Quick HUD suspended、Win session、AltGr、Game Guard、应用 snapshot、Center、SelectionStore、Input Recovery 与现有 Full Guide NORMAL 行为。

自动化无法替代的仍是 Windows 实机输入 smoke：尤其是物理 Win/Win chord、字母不落入原应用、混合 DPI 副屏与真实字体下的焦点感知。本阶段不把这些标成自动验证完成。

## 自动门禁与成本样本

- KeyPath、Catalog、Full Guide 与输入所有权针对性回归：77 项通过。
- 完整 unittest：509 项通过。
- Pack validator：通过；8 个 shipping Pack 本地化审计：574 条、0 warning；`git diff --check`：通过。
- 当前 VS Code 95 条 resolved rows、13 个 category 的纯内存 KeyPath dataset 构建，开发机 1000 次样本均值约 2.00 ms；300 个同层 hint 的 overflow 分配均值约 0.16 ms。

这些是单机微基准，不是 UI 首帧或热键到结果的统计分位数。KeyPath 不增加 idle timer、polling、线程、磁盘或网络成本；Qt widget 绘制和真实字体/DPI 仍以用户 smoke 为准。
