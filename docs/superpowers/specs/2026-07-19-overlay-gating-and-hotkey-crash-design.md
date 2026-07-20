# SigTouch v1.6 设计文档:置顶门控、Dock 收起与授权闪退防御

日期:2026-07-19
状态:已确认
关联:v1.2 §3(原生置顶)、v1.1 §5(降级状态机)、v1.5(状态同步)

## 1. 三项需求与决策

| # | 需求 | 决策 |
|---|---|---|
| 1 | 只有"启动状态"才需要窗口保持最前 | Overlay 置顶(原生层级 + 每秒 raise)**仅在 `_ui_state == "active"` 时生效**;paused/permission/error 时降级为普通层级并隐藏 Overlay |
| 2 | 窗口能关闭到状态栏收起,不妨碍其他操作 | 关窗即隐藏到托盘(现状已如此,补测试固化);新增 macOS `LSUIElement`——不占 Dock、不进应用切换器 |
| 3 | 勾选输入监控权限时闪退 | 权限从无到有时**不抢建** pynput 监听器,改为在向导中提示"重启后生效"并提供重启按钮 |

## 2. 崩溃调查结论(记录备查)

**已排除**:我方 pyobjc/ctypes 代码崩溃——用户复现当日无任何崩溃报告(`~/Library/Logs/DiagnosticReports/` 无 `SigTouch-*.ips`),且崩溃需加载的 AppKit/IOKit/ApplicationServices 框架在历史报告中从未出现。7-18 的两份 `Python-*.ips`(SIGSEGV at 0x1,pyobjc `class_call → objc_msgSend`)经核实是 v1.2 开发期为验证"offscreen 下 winId 占位句柄喂给 objc 会段错误"而**故意制造的受控复现**,该问题当时已用 `platformName() == "cocoa"` 门控修复。

**判定根因**:macOS 对 `kTCCServiceListenEvent`(输入监控)授权变更的系统行为——勾选权限时系统直接终止目标进程。SIGKILL 不生成崩溃报告,与"无报告 + 仅在勾选瞬间发生 + 打包 .app"三项观察完全吻合。加剧因素:v1.1 的 2 秒权限轮询会在勾选后立刻调 `_setup_hotkey()` 创建 CGEventTap,正撞 TCC 状态切换窗口。

**待确认实证**(不阻塞本设计):用户复现后执行
`log show --last 5m --predicate 'eventMessage CONTAINS[c] "sigtouch"' --style compact | tail -30`
可区分"系统 SIGKILL"与"tap 创建崩溃"。**两种根因的修复方案相同**(不抢建监听器),故先行实施。

## 3. 置顶门控(需求 1)

### 3.1 native 层

`sigtouch/ui/native.py` 新增:

```python
def unpin_window_topmost(widget) -> None
    # darwin:NSWindow.setLevel_(0 = NSNormalWindowLevel),
    #        collectionBehavior 复位为 0(默认);非 darwin no-op;fail-open。
    # 与 pin_window_topmost 同样 platformName() == "cocoa" 门控(勿删,offscreen 会段错误)。
```

### 3.2 Overlay 层

`sigtouch/ui/overlay.py` 新增 `set_topmost(enabled: bool)`:
- `True` → `show()` + `pin_window_topmost(self)`;
- `False` → `unpin_window_topmost(self)` + `hide()`(不使用时连影子一起收起,彻底不干扰)。
- 幂等:重复同值调用不重复操作(内部 `_topmost` 标志)。

`apply_screen()` 保持"设几何 + show + pin"语义不变(供初次布局与显示器切换使用),但由 app 决定何时调用。

### 3.3 app 层

- `_apply_state(state)` 内新增:`self._overlay.set_topmost(state == "active")`——状态是唯一驱动源,复用 v1.5 的单一入口。
- `_check_watchdog` 里每秒 `raise_()` 加门控:仅 `self._ui_state == "active"` 时执行。
- `_on_result` 的 `overlay.update_hand/clear` 不变(非 active 时 Overlay 已 hide,绘制无副作用)。

## 4. Dock 收起(需求 2)

- `packaging/sigtouch.spec` 的 `BUNDLE(info_plist=...)` 增加 `"LSUIElement": True`——应用不出现在 Dock 与 Cmd-Tab 切换器,仅托盘常驻,符合"不妨碍其他正常操作"。
- 设置窗/权限向导的关闭行为(点关闭仅隐藏、应用继续在托盘运行)现已如此(`app.setQuitOnLastWindowClosed(False)` + 关闭按钮走 `close()`),本版**补自动化测试固化该契约**,防止回归。
- 副作用与取舍:`LSUIElement` 下应用无菜单栏、窗口需经托盘菜单唤起——这正是期望形态(托盘应用)。已在 manual-qa 注明首次使用需从托盘打开设置。

## 5. 授权闪退防御(需求 3)

### 5.1 不抢建监听器

`sigtouch/app.py` `_ensure_capabilities()` 现逻辑:输入监控就绪即 `_setup_hotkey()`。改为:

- 记录**启动时**的输入监控权限快照 `self._im_granted_at_start: bool`(`__init__` 中 `perms.check(INPUT_MONITORING)`)。
- `_ensure_capabilities` 仅在 `self._im_granted_at_start` 为 True 时才启动监听器;若启动时无权限、运行中才授予,**不创建 event tap**,而是置 `self._hotkey_needs_restart = True`。
- 理由:避开 TCC 状态切换窗口(系统在此刻可能终止进程),且 macOS 本就要求重启应用才能使输入监控权限真正生效。

### 5.2 向导提示与重启

`sigtouch/ui/permission_wizard.py`:
- 新增可选注入 `restart_hint: Callable[[], bool] | None`(默认 None);向导在输入监控卡片下方显示一行提示:当 `restart_hint()` 为 True 时显示「⚠️ 快捷键需重启应用后生效」+「重启应用」按钮。
- 「重启应用」按钮发信号 `restart_requested`,由 app 处理。

`sigtouch/app.py`:
- 构造向导时传入 `restart_hint=lambda: self._hotkey_needs_restart`;连接 `restart_requested` → `_restart_app()`。
- `_restart_app()`:清理(停 watchdog/hotkey/vision、`release_all`),然后 `QApplication.quit()` 后用 `subprocess.Popen` 重新拉起自身——冻结态用 `sys.executable`(即 .app 内的可执行文件),开发态用 `sys.executable -m sigtouch`;失败仅记录日志并提示用户手动重启(不得抛出)。

### 5.3 其余权限不受影响

摄像头与辅助功能仍走原有即时激活路径(它们不涉及 event tap,不受 TCC 终止行为影响)。

## 6. 测试策略

- `native.unpin_window_topmost`:非 darwin no-op、cocoa 门控、异常 fail-open(与 pin 同构)。
- `overlay.set_topmost`:True → 可见且调用 pin;False → 调用 unpin 且隐藏;幂等(重复调用不重复触发,用 monkeypatch 计数)。
- `app`:`_apply_state("active")` → overlay 置顶开;`"paused"/"permission"/"error"` → 关;watchdog raise 仅 active 触发。
- 关窗契约:设置窗/向导 `close()` 后 `isVisible()` 为 False 且 `QApplication.instance()` 未退出(offscreen)。
- 闪退防御:启动时无输入监控权限 → 运行中授予后 `_setup_hotkey` **未**被调用且 `_hotkey_needs_restart` 为 True;启动时已有权限 → 正常启动监听器。
- `_restart_app`:monkeypatch `subprocess.Popen` 与 `quit`,断言清理顺序与重启命令构造(冻结/非冻结两分支)。
- manual-qa 第 16 项:暂停时 Overlay 不再压住其他窗口、恢复后重新置顶;Dock 无图标、Cmd-Tab 无条目、托盘可唤起设置;勾选输入监控权限**不再闪退**,向导显示重启提示,点重启后快捷键生效。

## 7. 明确不做(v1.6)

- 自动在权限授予后无缝启用快捷键(macOS 限制,必须重启)。
- Windows/Linux 的 Dock 等价物(无此概念;任务栏行为不变)。
- 崩溃根因的进一步内核级取证(修复方案对两种根因均有效)。
