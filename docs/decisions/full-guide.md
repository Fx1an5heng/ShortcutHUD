# Full Guide v1 / Polish v1.1 / Interaction v1.2

状态：v1.2 + Final Visual Polish implemented，等待 Windows 用户视觉 smoke。范围是当前应用查询、Guide 内累积 modifier 筛选和单条 Quick HUD Pin，不扩展 Pack，也不把个人选择写进产品默认值。

## 三个界面的职责

| 界面 | 入口与输入所有权 | 内容 / 写入 |
| --- | --- | --- |
| Quick HUD | 按住 modifier；无焦点、不消费输入 | 个人选择；8 条 cap；本阶段不变 |
| Full Guide | 独立全局命令；仅 active + focused 时拥有交互输入 | 当前应用已收录内容；可对 Quick HUD eligible 的 APP 条目逐条 Pin，不承担批量管理 |
| Shortcut Center | 主动打开管理界面 | 跨应用浏览、USER 编辑、Quick HUD 选择 |

## 唤起与生命周期

开发默认值为 `Ctrl+Shift+F10`：避开常用编辑组合和 Win 系统保留组合，不承诺在每台机器都无冲突。用户可从托盘或“设置 → Full Guide 快捷键”立即修改。

RegisterHotKey 能检测全局注册冲突，不能发现前台软件内部所有局部绑定；遇到此类冲突仍需用户选择其它组合。

`FullGuideHotkey` 在 Qt 主线程使用 `RegisterHotKey(NULL, id, MOD_NOREPEAT | modifiers, vk)`；原生过滤器仅消费本服务 ID 的 WM_HOTKEY。更换时先注册新的 ID，成功再注销旧 ID；失败保留旧注册，显示错误且不保存配置。默认键只通过 get-setting fallback 读取，不添加启动时自动落盘的默认字段。仅用户明确保存成功的新组合才更新 settings。

v1 接受 Ctrl/Alt/Shift 加字母、数字、功能键或导航键；拒绝裸 modifier、序列、F12、Win 组合和已知系统导航组合。右 Alt 按下时不执行唤起，保持 AltGr fail-closed。没有改动 KeyboardHandler、`suppress=False` 或 WinDiscoveryProxy。

生命周期：捕获前台 → 解析内存 Catalog → 标记 Guide active、取消 Quick HUD pending、隐藏 Quick HUD → 显示窗口。再次 hotkey / 干净状态 Esc / 关闭按钮 / WindowDeactivate 均关闭。只要存在 modifier filter 或文本查询，Esc 就一次清空两者并恢复完整 Guide；不会逐层 pop。已有应用模态设置/录制器拥有输入时不另开 Guide，避免出现无法接受 Esc 的被阻挡窗口。

Guide 期间仍接受 modifier 状态传播和 Input State Reconciler 恢复。关闭后若 modifier 仍按住，等待一次完整释放再重新调度 Quick HUD；不伪造 key-up、不修改输入 set、不调整 150/300 ms 延迟。

## v1.2 modifier 筛选与输入所有权

modifier filter 是 Guide 自己的导航状态，不镜像 KeyboardHandler 的物理按键集合。用户完整点按一个 modifier 并松开后才加入筛选；重复 modifier 是 no-op，显示顺序固定为 Ctrl、Alt、Shift、Win。因此 `[] → Ctrl → Ctrl+Shift` 是累积筛选，不要求持续按住，也没有 history stack。任意筛选或查询存在时，Esc 统一清空全部状态；再次 Esc 才关闭 Guide。

筛选依据仅为 trigger 第一 stroke 的 modifier set。Ctrl 同时匹配 Ctrl+P、Ctrl+Shift+P 和 Ctrl+K Ctrl+S；Ctrl+Shift 会排除 Ctrl+P；F5 等 single 在任意 modifier filter 下排除。数据流水线固定为 resolved/dedup → modifier subset filter → text terms → category/layout，中文和英文搜索都只作用于已筛选结果。

Ctrl、Alt、Shift 通过 Guide 自身 Qt key event 获取。Win 需要避免打开 Start 或执行 Win+E/Win+R，使用单独的低级键盘代理；该代理常驻消息线程但默认完全被动，只有 Guide active、窗口 focused 且仍为 foreground HWND 时才拥有并 suppress 物理 Win session。它成对接收左右 Win down/up；Win 持有期间的终止键也由同一 session 接管，因此系统组合不会泄漏。注入事件、非前台窗口、Guide 未激活时全部 fail open。关闭或失焦会同步清空代理 session，Windows 原生 Win 行为立即恢复。

这一实现没有改变 KeyboardHandler 的 `suppress=False`、Input State Reconciler、WinDiscoveryProxy 或现有 modifier delay。Guide input proxy 在 WinDiscoveryProxy 之后安装，使 active Guide 可以最先决定是否拥有 Win；非 Guide 生命周期仍沿用原发现链路。modifier tap 只有在同一 Guide session 内观察到 down 和 up、且中间没有终止键时才成立，所以打开 Guide 的 Ctrl+Shift+F10 只剩 release 时不会生成 Ctrl+Shift filter；AltGr 形态同样被终止键取消，保持 fail-closed。

## 前台和显示器快照

显式入口先同步刷新已有 ForegroundMonitor，不能依赖一秒前缓存。用已更新的 ApplicationIdentityRuntime、ApplicationDescriptorFactory、CatalogApplicationRegistry 构造友好应用名与产品身份，记录 HWND 和显示器。Guide 展示后即使自己成为前台，本次 snapshot 不再更换。

从本程序托盘/设置上下文唤起时，使用已有 tracker 的最后外部上下文，显示器回退到鼠标。无 HWND / 桌面同样使用鼠标显示器。正常外部应用用 MonitorFromWindow 的设备名匹配 Qt QScreen，并采用 Qt 的 logical geometry，避免把物理像素坐标直接当混合 DPI 的逻辑坐标。窗口覆盖目标 monitor 的完整逻辑区域，包括任务栏所在边缘，但不切换显示模式，也不是 exclusive fullscreen。

WPS 等异步身份若仍 pending，沿用已有 fail-closed 的未知逻辑身份；本次不等待或猜测文档类型，也不展示之前应用的数据。下一次唤起重新采样。窗口销毁、访问受限、显示器拔出时使用可用屏幕回退。

## 统一 Catalog 展示链路

`CatalogShortcutResolver.resolve_view()` 提供不受 Quick HUD eligibility / selections 限制的 resolved view。它与原 HUD 查询复用 USER 适配、隐藏规则和 canonical key identity；`catalog_presentation.py` 为 Guide 和 Center 共用的文本、分类和 trigger 展示值，继续调用现有 `select_catalog_text`，没有新的翻译系统。

层级为 USER_APP > APP > 可选 DEFAULT > GLOBAL。Guide 对未知应用不启用 DEFAULT，以便没有 user/global 时显示真实空状态。GLOBAL 以单独分类自然合并，不能覆盖 app-local 同键命令。用户条目显示“我的”。

combo、single、sequence、double_tap 都保留。raw Catalog 继续保存 provenance、stable ID 和 alias；Guide 消费的是只读 presentation groups，不删除或改写源记录。等价判定的硬边界是 application scope、完整 normalized trigger 和显式 context，证据只接受 stable ID/alias 交集、审校过的 `presentation_semantic_id` / legacy title，或相同英文 title + description。不得以 trigger、中文译文、模糊词义或数组位置猜测。

resolved presentation 的优先级保持 USER_APP > APP > 可选 DEFAULT > GLOBAL；APP 内同一等价组再按 native > imported upstream > legacy 选代表行。高层只覆盖低层的 trigger 冲突，同层中确有不同语义的记录继续并存，例如 F11 的全屏/调试单步和 Ctrl+N 的新文件/新聊天。搜索在 dedup 后的行上执行，但把同组旧文案作为搜索同义词保留。该策略不参与 Quick HUD selection migration，也不改变任何 stable ID。

VS Code raw Pack 仍为 133 条；Pack-only resolved Guide 是 95 条。合并 legacy 与 global 的完整产品视图由 146 条降至 108 条：38 个原始 repeated-trigger buckets 中，37 个有确定语义证据的等价组移除 38 条展示投影，最终仅两个确有不同上下文的同键组保留。覆盖数始终指当前 dedup 后 resolved view，不冒充软件完整快捷键数。

shipping zh_CN 必须是 Pack 内已经审校完成的最终文本。导入器只接受 exact phrase mapping，缺译文直接让开发期导入失败，不再拼接子串。独立 audit 只发 warning、不影响运行时加载，并允许 VS Code、Git、JSON、Markdown、PowerShell 等合理产品或技术名。Catalog/Center/Quick HUD/Guide 仍通过同一个 locale fallback 链路消费这些文本。

## 布局、搜索与成本

轻量 Qt Widgets 无边框置顶普通窗口，精确覆盖当前 monitor 的 logical geometry；不是 exclusive fullscreen。深色统一样式，不增加主题框架。

最终视觉优先级固定为 readability > visual cleanliness > scanning > density > one-screen。一屏只是 soft goal，不再通过缩字、压行或第 6 列强行实现。可用内容宽度按约 320 logical px 的最小可读列宽和 18 px column gap 计算，最多 5 列；1920 通常 5 列、1536/1600 通常 4 列、1280 通常 3 列，极窄窗口才安全降到 1/2 列。

分类估高只包含固定单行 entry、轻量 heading 和 section gap，不再因 description 长度假设多行。sequential balanced planner 先求平均目标高度，再按原始 category 顺序把连续 section 切给各列；不能回到 shortest-column masonry，也不能拆 category。搜索或 modifier 改变结果时重新计算完整 plan。自然放不下就使用唯一的整体纵向 scroll；始终无横向、分类内部 scroll 或分类内部双列。

presentation 采用 fullscreen cheat sheet，而不是 dashboard card：category 只有标题、数量、淡 separator 和留白，section 无圆角外框/实心 card 背景。每个 entry 是固定高度的单行 trigger/description/pin 三段布局；trigger 起点和 description 起点稳定，溢出使用 right elide，完整文本保留在 tooltip，hover 只显示轻微背景。

每次 session 从内存构造搜索文本，包含完整 trigger、中英文标题/描述、aliases 和分类文本。查询按空白分词、忽略大小写、所有词均匹配；输入和 resize 使用 35 ms 单次合并重排，关闭即停止。没有 idle polling，没有网络、webview 或激活时重读 Pack。

计数与搜索都基于同一批 dedup 后行；搜索状态显示“找到 X / 已收录 N”，不会从 raw sources 再生成重复结果。估高是确定性的单行近似，不追求像素级等高；超长 trigger、字体和 DPI 可能改变实际 elide，但不会改变 section 顺序。300 条压力验证支持整体滚动方案，不提前引入虚拟列表或第三方布局框架。

## Suppression

复用已有 PresentationIntent：HARD_BLOCK 禁止显式 Guide，进入 HARD_BLOCK 也关闭已开会话；SOFT_BLOCK 只阻止 passive Quick HUD，不阻止显式 Guide。没有新增应用特判或自动游戏检测。

## Quick HUD Pin 数据边界

Pin 只对 APP scope、`quick_hud` visible 且 trigger eligible 的 Catalog 条目开放；single、sequence 等 Catalog-only 条目不显示可点击星标。UI 只发出目标 stable ID 和期望状态，实际变更复用 QuickHudSelectionStore 的原子保存。

Full Guide 的交互星号只有 Quick HUD Pin 一种语义；recommended metadata 仅保留排序含义，不再绘制第二颗星。已 Pin 的 `★` 以低对比度始终显示；未 Pin 的固定区域保持 22 logical px 占位，默认文本为空，仅在该 entry hover 或 Pin 控件获得 keyboard focus 时显示 `☆`，因此 description 不会左右跳动。

已有 explicit selection 时，Pin 只在末尾追加目标 current stable ID；Unpin 只删除目标 ID 及其声明过的 aliases。其它应用、原顺序、unknown/stale IDs 均保持。explicit empty 仍代表用户明确清空，第一次 Pin 只加入目标项。应用从未配置时，第一次 Pin 才把当前 effective recommended 顺序物化后追加目标；Unpin recommended 则物化 recommended-minus-target。保存失败时内存状态回滚，不让 Controller 与磁盘形成假成功。

29 项事故恢复数据不进入 Pack、recommended 或产品特判。自动测试只注入 TemporaryDirectory 下的 store；真实选择恢复流程不重跑，现有 configured / empty / missing / stale / aliases / ordered upgrade 回归全部保留。

## 安全和验收边界

自动测试验证数据、dedup、本地化审计和 Qt 行为，独立 Windows probe 验证 RegisterHotKey 冲突与线程消息。真实物理按键触发、跨应用焦点、混合 DPI 副屏和 fullscreen 的最终体验仍需用户 smoke。v1.1 已逐条审校 8 个 shipping Pack 的 574 条中文并把开发审计 warning 清零；最终措辞观感仍接受人工验收。
