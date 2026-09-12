# Full Guide v1

状态：Implemented，等待 Windows 用户 smoke。范围是当前应用的只读查询，不扩展 Pack 或改写个人选择。

## 三个界面的职责

| 界面 | 入口与输入所有权 | 内容 / 写入 |
| --- | --- | --- |
| Quick HUD | 按住 modifier；无焦点、不消费输入 | 个人选择；8 条 cap；本阶段不变 |
| Full Guide | 独立全局命令；本窗口拥有搜索和 Esc | 当前应用已收录内容；无选择、编辑、应用切换控件 |
| Shortcut Center | 主动打开管理界面 | 跨应用浏览、USER 编辑、Quick HUD 选择 |

## 唤起与生命周期

开发默认值为 `Ctrl+Shift+F10`：避开常用编辑组合和 Win 系统保留组合，不承诺在每台机器都无冲突。用户可从托盘或“设置 → Full Guide 快捷键”立即修改。

RegisterHotKey 能检测全局注册冲突，不能发现前台软件内部所有局部绑定；遇到此类冲突仍需用户选择其它组合。

`FullGuideHotkey` 在 Qt 主线程使用 `RegisterHotKey(NULL, id, MOD_NOREPEAT | modifiers, vk)`；原生过滤器仅消费本服务 ID 的 WM_HOTKEY。更换时先注册新的 ID，成功再注销旧 ID；失败保留旧注册，显示错误且不保存配置。默认键只通过 get-setting fallback 读取，不添加启动时自动落盘的默认字段。仅用户明确保存成功的新组合才更新 settings。

v1 接受 Ctrl/Alt/Shift 加字母、数字、功能键或导航键；拒绝裸 modifier、序列、F12、Win 组合和已知系统导航组合。右 Alt 按下时不执行唤起，保持 AltGr fail-closed。没有改动 KeyboardHandler、`suppress=False` 或 WinDiscoveryProxy。

生命周期：捕获前台 → 解析内存 Catalog → 标记 Guide active、取消 Quick HUD pending、隐藏 Quick HUD → 显示窗口。再次 hotkey / 空查询 Esc / 关闭按钮 / WindowDeactivate 均关闭。非空查询的第一次 Esc 清空，Ctrl+F 聚焦并选中查询。已有应用模态设置/录制器拥有输入时不另开 Guide，避免出现无法接受 Esc 的被阻挡窗口。

Guide 期间仍接受 modifier 状态传播和 Input State Reconciler 恢复。关闭后若 modifier 仍按住，等待一次完整释放再重新调度 Quick HUD；不伪造 key-up、不修改输入 set、不调整 150/300 ms 延迟。

## 前台和显示器快照

显式入口先同步刷新已有 ForegroundMonitor，不能依赖一秒前缓存。用已更新的 ApplicationIdentityRuntime、ApplicationDescriptorFactory、CatalogApplicationRegistry 构造友好应用名与产品身份，记录 HWND 和显示器。Guide 展示后即使自己成为前台，本次 snapshot 不再更换。

从本程序托盘/设置上下文唤起时，使用已有 tracker 的最后外部上下文，显示器回退到鼠标。无 HWND / 桌面同样使用鼠标显示器。正常外部应用用 MonitorFromWindow 的设备名匹配 Qt QScreen，并采用 Qt 的 logical availableGeometry，避免把物理像素坐标直接当混合 DPI 的逻辑坐标。

WPS 等异步身份若仍 pending，沿用已有 fail-closed 的未知逻辑身份；本次不等待或猜测文档类型，也不展示之前应用的数据。下一次唤起重新采样。窗口销毁、访问受限、显示器拔出时使用可用屏幕回退。

## 统一 Catalog 展示链路

`CatalogShortcutResolver.resolve_view()` 提供不受 Quick HUD eligibility / selections 限制的 resolved view。它与原 HUD 查询复用 USER 适配、隐藏规则和 canonical key identity；`catalog_presentation.py` 为 Guide 和 Center 共用的文本、分类和 trigger 展示值，继续调用现有 `select_catalog_text`，没有新的翻译系统。

层级为 USER_APP > APP > 可选 DEFAULT > GLOBAL。Guide 对未知应用不启用 DEFAULT，以便没有 user/global 时显示真实空状态。GLOBAL 以单独分类自然合并，不能覆盖 app-local 同键命令。用户条目显示“我的”。

combo、single、sequence、double_tap 都保留；旧兼容条目与正式 Pack 同 trigger 时优先 Pack。正式 Pack 内不同 stable ID 即使同键也保留：F11 可以分别代表全屏和调试单步；没有上下文条件数据时不得凭描述猜测合并。本阶段因此如实保留历史 pilot/import 重叠条目，也不重写 IDs。推荐元数据仅参与原分类内排序和星标。

Pack-only VS Code 查询有 133 条；实际合并 legacy 非重复项和 GLOBAL 后可超过 133。覆盖数指当前 resolved view 中的已收录条目，不冒充软件完整快捷键数。

## 布局、搜索与成本

轻量 Qt Widgets 无边框置顶普通窗口，占当前工作区大部分，保留 8–28 logical px 边距；不是 exclusive fullscreen。深色统一样式，不增加主题框架。

分类按预计高度贪心分给当前最短列，平局选左列，结果确定。按约 350 logical px 每列自动选择，通常为 3/4/5 列，窄屏可退至 1/2；用户列数建议仍受实际宽度限制。只有一个内容纵向滚动区，无横向滚动、分页、分类内滚动条。

每次 session 从内存构造搜索文本，包含完整 trigger、中英文标题/描述、aliases 和分类文本。查询按空白分词、忽略大小写、所有词均匹配；输入和 resize 使用 35 ms 单次合并重排，关闭即停止。没有 idle polling，没有网络、webview 或激活时重读 Pack。

估高不是精确 masonry；字体、长描述和实际换行会造成列高差异。300 条压力验证支持当前简单方案，不提前引入虚拟列表或第三方布局框架。

## Suppression

复用已有 PresentationIntent：HARD_BLOCK 禁止显式 Guide，进入 HARD_BLOCK 也关闭已开会话；SOFT_BLOCK 只阻止 passive Quick HUD，不阻止显式 Guide。没有新增应用特判或自动游戏检测。

## 安全和验收边界

Guide 没有 selection store 引用或保存入口。真实选择恢复流程不重跑，测试仅注入临时存储；现有 configured / empty / missing / stale / aliases / ordered upgrade 回归全部保留。

自动测试验证数据和 Qt 行为，独立 Windows probe 验证 RegisterHotKey 冲突与线程消息。真实物理按键触发、跨应用焦点、混合 DPI 副屏和 fullscreen 的最终体验仍需用户 smoke。字体和 Pack 现存中英混合文本质量不是此次窗口测试能证明正确的内容。
