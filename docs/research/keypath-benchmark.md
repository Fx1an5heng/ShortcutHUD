# KeyPath v1 interaction benchmark

研究时间：2026-09-14。研究对象仅用于提炼交互与架构，没有复制第三方源码。

## which-key

[which-key.nvim 官方 README](https://github.com/folke/which-key.nvim/blob/main/README.md)把未完成的按键前缀作为上下文，只展示此时可继续输入的 group/action；当前按键和描述被并列显示，footer 明确列出可用导航。其默认交互是按键进入 group 或执行 binding，Esc 取消，Backspace 返回上一级，并支持稳定排序与有限空间下的滚动。

适合 KeyPath 的部分：

- 每个层级只显示当前可选的下一步，避免一次展示全部组合。
- hint、描述、group 层级和 breadcrumb 是彼此独立的数据。
- Backspace 表示层级返回，Esc 表示离开当前模式。
- 同一输入上下文要有稳定排序，不能依赖 widget 创建顺序。

不采用的部分：

- KeyPath 不代理真实 shortcut prefix，也不执行最终 binding。
- 不引入 popup delay、编辑器 mode、插件 icon、分页或 hydra 执行模式。

## Microsoft Office KeyTips / Windows access keys

[Windows access key 官方设计指南](https://learn.microsoft.com/en-us/windows/apps/develop/input/access-keys)强调：access key 是顺序输入的一到多个字母/数字；大量命令应分成独立 scope，以减少认知负担；单字符优先，通常不超过两字符；同一 scope 必须避免重复和前缀冲突。指南还建议使用稳定、可记忆的既有 mnemonic，而不是任意位置或本地化 UI 排序。

[Microsoft 365 Ribbon 官方说明](https://support.microsoft.com/en-us/accessibility/windows/use-the-keyboard-to-work-with-the-ribbon)展示了 root tab → command 的多层 KeyTip：每层只接受当前显示的一到两个字符，并持续显示下一层选项。Office 自身对 Esc/返回的细节与 ShortcutHUD 不完全相同，因此 KeyPath 按本产品已经确认的规则使用 Backspace 返回层级、Esc 一次退出模式。

[Office Add-ins KeyTips 官方文档](https://learn.microsoft.com/en-us/office/dev/add-ins/design/add-custom-key-tips)说明宿主会检查冲突，并在冲突时分配确定性 fallback。KeyPath 不照搬其 `Y1` 规则，但采用相同原则：同一 scope 的 hint 唯一、无前缀冲突、fallback 可重复计算。

适合 KeyPath 的部分：

- ROOT category 与 CATEGORY action 是两个独立 hint scope，可在不同 scope 复用同一字符。
- stable category key / English semantic text 决定 mnemonic；当前中文翻译只负责展示。
- 当前少于 36 项时优先单字符；未来溢出时同层整体切到固定长度的两字符，避免 `A` 与 `A1` 同时存在导致不可达。

## ShortcutHUD 现有边界

Full Guide 已经提供 resolved/dedup presentation、modifier filter、text search、Quick Pin、前台 snapshot 和 active/focused 输入所有权。KeyPath 必须消费进入时已经可见的 rows，不重新解析 Catalog、不重读前台应用，也不改变 filter/query/scroll。

NORMAL 与 KEYPATH 是同一个 Guide session 的内部 mode：

- NORMAL：现有 search、modifier、Esc、Pin 全部不变；Tab 进入 KeyPath。
- KEYPATH：字母/数字只选择 hint；modifier 不改变 filter；Backspace 返回一层；Esc 回 NORMAL。
- 再次 activation hotkey 仍由既有 Controller toggle 关闭整个 Guide。
- Quick HUD 继续 suspended，Win suppression 继续由现有 Guide input service 负责。

## v1 决策

1. 使用纯 `KeyPathHintAllocator`，输入 stable identity、preferred hint 和 English/alias semantic sources，输出确定性且无冲突的 hint。
2. 使用纯 `KeyPathSession` 表达 ROOT、CATEGORY、RESULT；UI 只渲染 session 并发送 hint/category/action intent。
3. category preferred mnemonic 是跨 locale 的稳定产品映射；action mnemonic 从 English title/description、aliases、stable identity 依次提取。
4. <=36 个选项使用单字符 A-Z/0-9；>36 时同层全部使用确定性两字符，避免前缀歧义并保证不 crash。
5. RESULT 只突出显示命令描述和真实 shortcut，不调用 automation、不发送按键、不执行应用命令。
6. KeyPath 进入时冻结当前 visible dataset，退出时恢复原 query、modifier、scroll 和 search focus。

## 明确 defer

- Hover Demo、asset system、命令执行、学习统计、quiz、bookmark。
- Developer Navigator / Command Center 内容树。
- 自动 app 切换、Pack 重读、网络检索、后台 polling。
