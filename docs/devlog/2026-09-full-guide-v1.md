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

预览也如实暴露旧 Pack 的重叠记录和中英混合描述。此次没有借机重新导入、改 ID 或猜测合并；这些内容质量问题保留为后续独立审查事项。

## 验证结果与局限

- 完整 unittest：445 项通过；相对 403 基线新增 42 项。
- Pack validator：通过；git diff --check：通过。
- 数据：4 类 trigger、所有 shipping Catalog-only、VS Code 133 条、user/global 优先级、中英文及 fallback、搜索、确定性分组与 300 条压力数据。
- Qt/状态：toggle、Ctrl+F、Esc 两阶段、失活关闭、未知应用不沿用旧行、语言切换、pending/visible Quick HUD 清理、Win 重入、HARD/SOFT。
- 真实应用启动的隔离子进程：用明确临时路径装配主程序，启动、查询、toggle 和注册失败不改变四个 fixture 文件的 bytes/mtime；成功的用户热键保存只改变临时 settings。
- 最后再只读核对恢复后的全应用选择及真实 selection/user shortcuts/settings 哈希；与开始前一致。浏览器没有被遗漏。

本机隔离 offscreen 一次样本：146 条合并视图解析约 1.83 ms、首次 render/processEvents 约 102.66 ms、搜索约 5.85 ms；300 条合成视图约 110.67 ms、搜索约 6.86 ms。不是统计分位数，不含系统快捷键到首帧的端到端延迟；输入另有 35 ms 单次合并重排。idle 没有新增循环轮询，Catalog 不重读。

还需要用户验证实际焦点、物理热键、第二显示器/混合 DPI、普通 fullscreen SOFT_BLOCK 和 Manual Game Mode HARD_BLOCK。没有宣称已完成人工验收，也没有自动重启用户正在运行的旧实例。

## Smoke 清单

1. 退出旧实例并启动本分支。在 VS Code 按 `Ctrl+Shift+F10`：友好标题、近满工作区分类布局，看到 F5、F11、Ctrl/Alt/Shift 和 Ctrl+K Ctrl+S。
2. 搜索 `terminal`、`终端`、`Ctrl+K`；Ctrl+F 返回搜索；Esc 先清查询再退出。再次热键关闭。
3. Guide 打开期间 Quick HUD 不弹；关闭、释放 modifier 后，新按 Ctrl 恢复原先手选内容。浏览器也核对原先选择。
4. VS Code 放副屏后打开，同屏显示；点击另一软件后 Guide 自动关闭，不抢回焦点。
5. Manual Game Mode ON 不打开；OFF 不用重启；普通 fullscreen SOFT_BLOCK 仍允许显式打开。
6. 未知软件正确展示 user/global 或空状态，不残留 VS Code。设置中修改热键；冲突提示后旧键仍工作。
