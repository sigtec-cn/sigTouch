# SigTouch v1.5 设计文档:启停状态与快捷键界面明示

日期:2026-07-19
状态:已确认
关联:v1.1 §5(降级状态机、_toggle_pause、pause_hotkey)、v1.3(主题、设置窗、托盘)

## 1. 背景与决策

现状:v1.1 已有全局快捷键(pynput GlobalHotKeys,默认 `<ctrl>+<alt>+p`)驱动 `_toggle_pause`,即"暂停/恢复"就是"不使用/使用";托盘 tooltip 已显示状态。缺的是**界面对状态与快捷键的显式呈现**——用户不知道当前在不在用、也不知道用什么键切换。

| 决策 | 结论 |
|---|---|
| 切换键 | 沿用现有 `general/pause_hotkey`(默认 Ctrl+Alt+P),**不新增、不改默认**(Ctrl+S 与"保存"重叠,已与用户确认放弃) |
| 快捷键人读化 | 新增纯函数把 pynput 语法转人读字符串 |
| 状态呈现位置 | 设置窗顶部状态条 + 托盘(tooltip 与切换菜单项) |
| Overlay 是否显示 | 不显示(避免遮挡内容;托盘+设置已足够) |

本版为纯呈现层增强,**不改动启停逻辑本身**。

## 2. 快捷键人读化(新增 `sigtouch/interaction/hotkey.py`,纯 Python)

```python
def format_hotkey(combo: str) -> str
    # "<ctrl>+<alt>+p" -> "Ctrl+Alt+P";"<cmd>+<shift>+s" -> "Cmd+Shift+S"
    # 空串或纯空白 -> "未设置"
    # 规则:按 "+" 分段,去 <>,每段首字母大写(已知修饰键名做规范映射,
    #       单字符键大写);未知段原样标题化。
```

- 放 `interaction/`(纯逻辑,无 GUI 依赖,符合纯度约束,便于单测)。
- 修饰键规范映射:`ctrl→Ctrl, alt→Alt, cmd→Cmd, shift→Shift, ctrl_l/ctrl_r→Ctrl` 等常见别名;其余段 `.strip("<>").title()`。

## 3. 设置窗状态条(`sigtouch/ui/settings_dialog.py`)

- 在导航+页面区**之上**新增一张状态卡(`QFrame[class="card"]`),常驻所有页可见:
  - 第一行:状态徽章 `QLabel`(圆点 + 文案),按状态着色——
    - `active`:绿点「● 使用中」;`paused`:灰点「● 已暂停(不控制鼠标)」;
    - `permission`:黄点「● 等待权限授权」;`error`:红点「● 摄像头异常」。
  - 第二行:muted 文案「切换快捷键:<b>Ctrl+Alt+P</b>(在"通用"页可修改)」,快捷键实时取自 `format_hotkey(cfg.get("general/pause_hotkey"))`。
- 新增方法 `set_running_state(state: str)`:更新徽章文案+颜色(用 `theme.repolish` 抛光 class);`refresh_hotkey_label()`:重取配置刷新第二行。
- 通用页"暂停快捷键"文本框下方 muted 说明补一句「当前:Ctrl+Alt+P」,并在该键即时生效时调用 `refresh_hotkey_label()`(pause_hotkey 改动已触发 `settings_applied` 轻量路径 → app 侧会 `_setup_hotkey`;设置窗自身在 `_on_field_changed` 里若 key==pause_hotkey 顺带刷新状态条第二行)。
- 徽章颜色用主题 token(OK/TEXT_MUTED/WARN/DANGER),新增 QSS class `badge-dot-active/paused/permission/error` 或复用行内 setStyleSheet(实现取后者更简单,颜色来自 theme 常量)。

## 4. app 同步(`sigtouch/app.py`)

- `_refresh_tray_state()` 现有分支(paused/permission/error/active 判定)提取出一个 `_current_state() -> str` 供托盘与设置窗共用;`_refresh_tray_state` 末尾追加 `self._settings_dlg.set_running_state(self._current_state())`。
- 托盘打开前(`settings_requested` → 现连 `self._settings_dlg.show`)改接一个 `_show_settings()`:先 `set_running_state` + `refresh_hotkey_label` 再 `show`,保证每次打开状态是最新的。
- `_setup_hotkey()` 成功/跳过后无需额外动作(状态条快捷键在打开设置时刷新即可)。

## 5. 托盘(`sigtouch/ui/tray.py`)

- `set_state(state)` 增加可选 `hotkey_label: str = ""` 参数:tooltip 追加快捷键提示(如 `"SigTouch:运行中 (Ctrl+Alt+P 暂停)"`),切换菜单项文案追加 `" (Ctrl+Alt+P)"`。为空则退回原文案(向后兼容)。
- app 调用 `set_state` 时传入 `format_hotkey(...)`;`TrayController` 不自己读配置(保持无状态,依赖注入文案)。
- `_STATE_META` 结构不变(色/基础 tooltip/基础切换文案),hotkey 后缀在 `set_state` 内拼接。

## 6. 测试策略

- `format_hotkey`:pynput 典型串(ctrl+alt+p、cmd+shift+s、单键 f1、别名 ctrl_l)、空串/纯空格 →「未设置」、未知段标题化。纯函数单测。
- 设置窗:`set_running_state("paused")` 后徽章文案含「已暂停」;`refresh_hotkey_label()` 后第二行含 `format_hotkey` 结果;pause_hotkey 即时改动后状态条第二行更新(offscreen)。
- 托盘:`set_state("active", "Ctrl+Alt+P")` 后 tooltip 含快捷键、切换项文案含快捷键;`set_state("active")` 无后缀(兼容)。
- app:`_current_state()` 四态映射;`_refresh_tray_state` 调用 `set_running_state`(monkeypatch 记录);`_show_settings` 先同步后 show(stub 记录调用顺序)。
- manual-qa 第 15 项:打开设置见状态条(使用中/已暂停实时切换)、快捷键显示正确;按 Ctrl+Alt+P 托盘 tooltip 与设置状态条同步翻转;改快捷键后显示同步更新。

## 7. 明确不做(v1.5)

- 新增/更改切换键(仍 Ctrl+Alt+P)。
- Overlay 上显示状态。
- 图形化快捷键录制器(仍文本框输入 pynput 语法,只是补人读显示)。
- Windows/macOS 修饰键符号化(⌘⌥⇧;统一用 Ctrl/Alt/Cmd/Shift 文字,跨平台一致)。
