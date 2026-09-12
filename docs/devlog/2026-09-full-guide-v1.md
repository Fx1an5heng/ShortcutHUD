# 2026-09：Full Guide v1

实现与验证：2026-09-11；继续收尾：2026-09-12。

## 先证明上次事故没有重演

这次开始前最重要的门禁不是新窗口，而是已经恢复的用户选择。只读核对现有文件与批准过的本地 candidate，按每个应用、每组 modifier 的原顺序比较 resolver 输出，而不是只比较数量。没有重跑恢复，也没有把个人选择写进产品或测试 fixture。

旧分支门禁为 403 项测试、Pack validator 和 diff check。通过后将 Pack Expansion fast-forward 到本地 main，保留历史，显式推送 origin/main 到 `6fa81f4`；没有推 upstream、没有 tag/release。新工作位于 `feature/full-guide-v1`，用户原有 settings 修改一直排除在提交外。

## 数据能力终于与展示方式分开

KeyClu 的分组与当前应用流程值得借鉴；CheatSheet 提醒我们减少导航；当前 PowerToys 文档则提供了可搜索 Guide 的清晰退出规则。我们没有照抄其后台应用侧栏或常驻面板。Full Guide 是查询，管理依旧归 Center，按住修饰键依旧只得到小型 HUD。

实现初期一个真实失败是 VS Code 全量测试只得到 91 条，而不是 133 条。两个错误假设叠加：把 visibility 当 Guide 的排除条件，以及将所有同 trigger 项全局去重。旧 pilot 项仍合法存在，正式数据也包含上下文不同的同键命令。修正是保留全部正式 stable IDs，仅让更高来源覆盖更低来源的冲突，并消除 legacy bridge 与 Pack 的重复投影。不能为了漂亮数量重新推断语义，更不能改用户选择。

查询入口最终落在已有 CatalogShortcutResolver，而不是让窗口维护自己的快捷键数据库。Center 和 Guide 共用文本/分类/trigger 展示助手；Guide model 只做分组、搜索和列分配。自动断言同一 VS Code 条目的中英文描述与 Center、Quick HUD 一致。

## 显式窗口需要不同的输入边界

RegisterHotKey 负责一个命令，不改被动 hook。重注册失败不能先丢掉旧快捷键，因此使用两个轮换 ID，先申请新键再注销旧键。默认 `Ctrl+Shift+F10` 不在启动时写入 settings。还补了模态设置/录制器的边界：它们正在拥有输入时不打开一个无法接受 Esc 的 Guide。

Windows 独立 probe 实际注册 `Ctrl+Alt+Shift+F13`，第二个进程尝试同组合得到错误 1409；向测试进程自己的线程队列投递两次 WM_HOTKEY，Qt 原生过滤器接收两次。测试结束注销，没有向用户应用模拟键盘输入。这证明的是原生注册和消息通道，不冒充用户物理按键 smoke。

Guide 打开前同步刷新前台，并固定本次 descriptor/HWND/monitor。关闭后不伪造“所有键已松开”，而是保持现有 reconciliation 链路，让仍按住的 modifier 等释放后再开始。Win pending/discovery 清理、HARD/SOFT policy 和新一轮 Ctrl 调度都有测试。

## 界面迭代不是只看模型数量

使用 Qt 实际渲染了宽屏 5 列、窄屏 3 列和终端搜索状态。最初 offscreen 平台没有加载系统字体，连英文字母都显示方块；仅在本地预览器显式载入 Windows 字体解决，没有向产品塞机器字体路径。缩窄后的第一张截图抓到了延迟重排中间帧；等待 Qt 事件完成再复核，内容恢复正确，并增加真实 3/4/5 列、纵向滚动和无横向滚动的测试。

复用窗口还暴露了语言切换边界：仅在构造时翻译控件不足。补了 LanguageChange 更新，测试在同一个窗口中切换语言；内容每次激活仍从当前 locale 解析。推荐星标是元数据，不拼入描述，也不额外复制一组。

第一次用户视觉验收确认产品形态成立，也直接暴露两类不能带进验收版的问题：VS Code pilot、PowerToys import 与 legacy projection 在同一视图里重复；导入期的英文子串替换留下“Quick 打开”“显示 Problems”一类半中半英文。v1.1 把它们作为 presentation 与 shipping content 问题收口，没有改 ID、selection 或 Quick HUD 数量/顺序。

## Polish v1.1：用证据合并，而不是按键删行

仅按 trigger 去重曾经造成两种相反错误：既保留了 VS Code 中语义相同但 stable ID 不同的 41 条 pilot/import 投影，又会吞掉 PowerPoint 中同键但语义不同的 legacy 项。新的 presentation grouping 先用 app scope、完整 trigger、context 分桶，再只接受 stable alias、显式审校 semantic ID、审校 legacy title 或完全一致的英文 title + description 作为等价证据。代表项按 native、imported、legacy 的顺序选择；USER_APP / APP / DEFAULT / GLOBAL 的原层级不变。

VS Code 完整产品视图的 before 是 146：38 个 trigger bucket 含重复或同键项。人工核对出 37 个等价语义组（75 条源记录，其中一组有三条），presentation 移除 38 条后为 108；F11 的全屏/调试单步和 Ctrl+N 的新文件/新聊天仍各自保留。Pack-only 是 raw 133、resolved 95。其它七个 Pack 没有套用 VS Code 特判：File Explorer 43→43、Chrome 71→71、Edge 83→83、Excel 80→80、Word 104→104、Windows Terminal 64→64；PowerPoint 92→94，增加的两条正是旧 trigger-only 逻辑错误吞掉的“后移一层/置于底层”和“前移一层/置于顶层”不同语义，而非新增数据。

搜索只接收 dedup 后行，同时保留被合并记录的英文/中文搜索同义词。计数也改为同一 resolved 集合，因此不会出现列表已去重但标题仍报 raw 数量的双口径。

## Polish v1.1：shipping 中文是数据，不是运行时拼词

先运行审计得到 574 条、556 个 warning，再逐项检查 File Explorer、Chrome、Edge、Excel、PowerPoint、Word、VS Code、Windows Terminal 的 category/title/description。最终 exact translation table 生成 Pack 中可直接展示的中文；导入器缺少 exact 映射时失败，不再调用 substring translator。审计结束为 574 条、0 warning。仍出现的英文仅限审校 allowlist，例如 Visual Studio Code、VS Code、Git、JSON、Markdown、PowerShell、Microsoft、Chrome、Edge、Excel、PowerPoint、Word 和 InPrivate。

顶栏移除了用户可见的“5 列”选择器，仍按宽度自动选择 3/4/5 列，内部 hook 仅用于测试。推荐星号降低对比度，顶部间距略放宽。去重后 VS Code 最大分类从 35 行降到 23 行；实际 5 列、3 列和搜索截图没有横向滚动，因此分类内部双列本轮 defer，避免为已缓解的问题增加第二套布局规则。

## 验证结果与局限

- 完整 unittest：465 项通过；相对 403 基线新增 62 项。
- Pack validator：通过；git diff --check：通过。
- 数据：4 类 trigger、所有 shipping Catalog-only、37 个审校等价组、USER/native/imported/legacy/global 优先级、同键不同 context、stable alias、确定性及 300 条压力数据。
- 本地化：8 个 Pack 共 574 条、audit warning 556→0；known mixed-text sample、allowlist、English 不变、polish 幂等均有测试。
- Guide：resolved 计数、dedup 后搜索、recommended 不复制、F5/sequence、3/4/5 自动布局、无用户列数控件均有测试。
- Qt/状态：toggle、Ctrl+F、Esc 两阶段、失活关闭、未知应用不沿用旧行、语言切换、pending/visible Quick HUD 清理、Win 重入、HARD/SOFT。
- 真实应用启动的隔离子进程：用明确临时路径装配主程序，启动、查询、toggle 和注册失败不改变四个 fixture 文件的 bytes/mtime；成功的用户热键保存只改变临时 settings。
- 最后再只读核对恢复后的全应用选择及真实 selection/user shortcuts/settings 哈希；与开始前一致。浏览器没有被遗漏。

本机隔离 offscreen 的 v1.1 一次样本：108 条 VS Code 完整视图解析约 4.63 ms、首次 render/processEvents 约 78.81 ms、搜索约 5.30 ms；300 条合成视图约 100.83 ms、搜索约 6.99 ms。不是统计分位数，不含系统快捷键到首帧的端到端延迟；输入另有 35 ms 单次合并重排。dedup 是激活时的内存分桶，没有新增 idle polling、网络或 Pack 重读。

还需要用户验证实际焦点、物理热键、第二显示器/混合 DPI、普通 fullscreen SOFT_BLOCK 和 Manual Game Mode HARD_BLOCK。没有宣称已完成人工验收，也没有自动重启用户正在运行的旧实例。

## Smoke 清单

1. 退出旧实例并启动本分支。在 VS Code 打开 Guide：确认 Ctrl+C/X/V/Z/Y 与 Ctrl+K Ctrl+S 各只出现一次；F11 的两种语义和 sequence 仍存在。
2. 中文环境扫读 VS Code 与其它常用应用，不再出现“Go to Line”“Quick 打开”“显示 Problems”“替换 in Files”等混杂文案。
3. 顶部没有“5 列”选择器；宽/窄工作区仍自动得到合适的 5/3 列，只有纵向滚动。
4. 搜索 `terminal`、`终端`、`Ctrl+K`，确认结果和“找到 X / 已收录 N”无重复；Ctrl+F、Esc 两阶段、再次热键关闭仍正常。
5. Guide 打开期间 Quick HUD 不弹；关闭、释放 modifier 后，新按 Ctrl 恢复原先手选内容。浏览器也核对原先选择和顺序。
6. VS Code 放副屏后打开，同屏显示；点击另一软件后 Guide 自动关闭，不抢回焦点。
7. Manual Game Mode ON 不打开；OFF 不用重启；普通 fullscreen SOFT_BLOCK 仍允许显式打开。
8. 未知软件正确展示 user/global 或空状态，不残留 VS Code。设置中修改热键；冲突提示后旧键仍工作。
