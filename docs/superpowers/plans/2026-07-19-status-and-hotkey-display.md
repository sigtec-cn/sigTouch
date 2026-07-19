# SigTouch v1.5 实现计划:启停状态与快捷键界面明示

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 界面明示"使用/不使用"状态与切换快捷键(Ctrl+Alt+P):新纯函数人读化快捷键 → 设置窗顶部状态条 + 托盘 tooltip/菜单带快捷键,app 实时同步真实状态。切换逻辑本身不变。

**Architecture:** 纯函数 `interaction/hotkey.py` → 托盘 `set_state` 加可选 hotkey 后缀 → 设置窗顶部状态卡 + `set_running_state`/`refresh_hotkey_label` → app 提取 `_current_state()` 并在 `_refresh_tray_state`/`_show_settings` 同步给托盘和设置窗。

**Spec:** `docs/superpowers/specs/2026-07-19-status-and-hotkey-display-design.md`

## Global Constraints

- GUI 只能用 PySide6;`interaction/hotkey.py` 纯 Python(不得 import cv2/mediapipe/PySide6/pynput)。
- 切换逻辑不改:`_toggle_pause`/`_paused`/`pause_hotkey` 语义与默认值(`<ctrl>+<alt>+p`)不变。
- `TrayController.set_state` 新增参数带默认值 `hotkey_label=""`(空时退回原文案,向后兼容);`_STATE_META` 三元组结构不变。
- 设置窗兼容红线不变:`_fields`/`field_widget()`/`apply()`;新增方法不破坏 `_load`/即时生效。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`(基线 108);提交前缀规范同前,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 文件结构总览

```
sigtouch/interaction/hotkey.py       # format_hotkey 纯函数(Task 1)
tests/test_hotkey_format.py          # 新增(Task 1)
sigtouch/ui/tray.py                  # set_state hotkey_label 参数(Task 2)
tests/test_permission_wizard.py      # 托盘断言(既有文件含托盘测试)(Task 2)
sigtouch/ui/settings_dialog.py       # 状态卡 + set_running_state/refresh_hotkey_label(Task 3)
sigtouch/app.py                      # _current_state / 同步托盘+设置窗 / _show_settings(Task 3)
tests/test_settings_status.py        # 新增(Task 3)
tests/test_app_permissions.py        # 同步断言(Task 3)
docs/manual-qa.md                    # 第 15 项(Task 3)
```

---

### Task 1: 快捷键人读化纯函数

**Files:**
- Create: `sigtouch/interaction/hotkey.py`
- Test: `tests/test_hotkey_format.py`

**Interfaces:**
- Produces: `format_hotkey(combo: str) -> str`。Task 2/3 消费(托盘后缀、设置窗状态条)。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hotkey_format.py
from sigtouch.interaction.hotkey import format_hotkey


def test_ctrl_alt_p():
    assert format_hotkey("<ctrl>+<alt>+p") == "Ctrl+Alt+P"


def test_cmd_shift_s():
    assert format_hotkey("<cmd>+<shift>+s") == "Cmd+Shift+S"


def test_single_function_key():
    assert format_hotkey("<f1>") == "F1"


def test_modifier_side_aliases_normalized():
    assert format_hotkey("<ctrl_l>+a") == "Ctrl+A"


def test_empty_or_blank_is_unset():
    assert format_hotkey("") == "未设置"
    assert format_hotkey("   ") == "未设置"


def test_plain_letter():
    assert format_hotkey("a") == "A"


def test_unknown_segment_titlecased():
    assert format_hotkey("<ctrl>+<media_play>") == "Ctrl+Media_Play"
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_hotkey_format.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 2: 实现 hotkey.py**

```python
# sigtouch/interaction/hotkey.py
"""pynput GlobalHotKeys 组合串 → 人读字符串。纯 Python,便于单测。"""

_MODIFIER_NAMES = {
    "ctrl": "Ctrl", "ctrl_l": "Ctrl", "ctrl_r": "Ctrl",
    "alt": "Alt", "alt_l": "Alt", "alt_r": "Alt", "alt_gr": "Alt",
    "cmd": "Cmd", "cmd_l": "Cmd", "cmd_r": "Cmd",
    "shift": "Shift", "shift_l": "Shift", "shift_r": "Shift",
}


def _segment(raw: str) -> str:
    key = raw.strip().strip("<>").strip()
    if not key:
        return ""
    low = key.lower()
    if low in _MODIFIER_NAMES:
        return _MODIFIER_NAMES[low]
    if len(key) == 1:
        return key.upper()
    # 功能键/未知键:标题化(f1 -> F1, media_play -> Media_Play)
    return key.title()


def format_hotkey(combo: str) -> str:
    """把 "<ctrl>+<alt>+p" 转成 "Ctrl+Alt+P";空/纯空白返回 "未设置"。"""
    if not combo or not combo.strip():
        return "未设置"
    parts = [_segment(p) for p in combo.split("+")]
    parts = [p for p in parts if p]
    return "+".join(parts) if parts else "未设置"
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 108 + 7 = 115

```bash
git add sigtouch/interaction/hotkey.py tests/test_hotkey_format.py
git commit -m "feat: human-readable hotkey formatter"
```

---

### Task 2: 托盘 tooltip 与菜单带快捷键

**Files:**
- Modify: `sigtouch/ui/tray.py`, `tests/test_permission_wizard.py`(该文件含 `test_tray_permission_state_and_menu`)

**Interfaces:**
- Produces: `TrayController.set_state(state: str, hotkey_label: str = "")`——hotkey_label 非空时 tooltip 追加 `" ({hotkey} {动作})"`、切换菜单项文案追加 `" ({hotkey})"`;空时原文案。切换动作词取自 `_STATE_META` 第三元组去掉 emoji 前缀后的核心词(暂停/恢复)——实现为直接在 toggle_text 后接 `" ({hotkey})"`。

- [ ] **Step 1: 更新/新增托盘断言(先失败)**

`tests/test_permission_wizard.py` 的 `test_tray_permission_state_and_menu` 末尾追加(不改既有断言):

```python
    # 带快捷键:tooltip 与切换项文案含快捷键
    t.set_state("active", "Ctrl+Alt+P")
    assert "Ctrl+Alt+P" in t._tray.toolTip()
    assert "Ctrl+Alt+P" in t._toggle_action.text()
    # 不带快捷键:退回原文案(无括号后缀)
    t.set_state("active")
    assert "Ctrl+Alt+P" not in t._toggle_action.text()
    assert t._toggle_action.text() == "⏸ 暂停"
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_permission_wizard.py -v`
Expected: FAIL(set_state 不接受第二参数 / 无后缀)

- [ ] **Step 2: 修改 set_state**

`tray.py` 的 `set_state` 替换为:

```python
    def set_state(self, state: str, hotkey_label: str = "") -> None:
        color, tip, toggle_text = _STATE_META[state]
        self._tray.setIcon(make_icon(color))
        if hotkey_label:
            # 切换动作词 = 去掉 emoji 前缀的核心("⏸ 暂停" -> "暂停")
            action_word = toggle_text.split(" ", 1)[-1]
            self._tray.setToolTip(f"{tip} ({hotkey_label} {action_word})")
            self._toggle_action.setText(f"{toggle_text} ({hotkey_label})")
        else:
            self._tray.setToolTip(tip)
            self._toggle_action.setText(toggle_text)
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 115 全过

```bash
git add sigtouch/ui/tray.py tests/test_permission_wizard.py
git commit -m "feat: tray tooltip and toggle label show the pause hotkey"
```

---

### Task 3: 设置窗状态条与 app 同步

**Files:**
- Modify: `sigtouch/ui/settings_dialog.py`, `sigtouch/app.py`, `docs/manual-qa.md`
- Test: `tests/test_settings_status.py`(新增), `tests/test_app_permissions.py`(追加)

**Interfaces:**
- Produces:
  - `SettingsDialog.set_running_state(state: str)`(徽章文案+颜色)、`refresh_hotkey_label()`(第二行重取 `format_hotkey(cfg.get("general/pause_hotkey"))`);属性 `_status_badge`、`_hotkey_line`。
  - `SigTouchApp._current_state() -> str`("paused"|"permission"|"error"|"active");`_show_settings()`(先同步状态与快捷键后 show)。
- Consumes: `format_hotkey`(Task 1)、`set_state(state, hotkey_label)`(Task 2)。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_settings_status.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dlg(qapp, **backend):
    from sigtouch.ui.settings_dialog import SettingsDialog
    return SettingsDialog(Config(backend=backend))


def test_status_badge_reflects_state(qapp):
    dlg = _dlg(qapp)
    dlg.set_running_state("active")
    assert "使用中" in dlg._status_badge.text()
    dlg.set_running_state("paused")
    assert "已暂停" in dlg._status_badge.text()
    dlg.set_running_state("permission")
    assert "权限" in dlg._status_badge.text()
    dlg.set_running_state("error")
    assert "摄像头" in dlg._status_badge.text()


def test_hotkey_line_shows_formatted_key(qapp):
    dlg = _dlg(qapp, **{"general/pause_hotkey": "<ctrl>+<alt>+p"})
    dlg.refresh_hotkey_label()
    assert "Ctrl+Alt+P" in dlg._hotkey_line.text()


def test_hotkey_line_updates_on_field_change(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("general/pause_hotkey").setText("<cmd>+<shift>+s")
    dlg.field_widget("general/pause_hotkey").editingFinished.emit()
    assert "Cmd+Shift+S" in dlg._hotkey_line.text()
```

`tests/test_app_permissions.py` 追加:

```python
def test_refresh_tray_state_syncs_settings_dialog(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    a = _make_app(monkeypatch)
    synced = []
    monkeypatch.setattr(a._settings_dlg, "set_running_state",
                        lambda s: synced.append(s))
    a._paused = True
    a._refresh_tray_state()
    assert synced == ["paused"]      # 托盘刷新时同步设置窗
    assert a._current_state() == "paused"
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_status.py tests/test_app_permissions.py -v`
Expected: FAIL(无 set_running_state / _current_state)

- [ ] **Step 2: 设置窗状态卡**

`settings_dialog.py`:
1. import 追加 `from sigtouch.interaction.hotkey import format_hotkey` 与 `from sigtouch.ui import theme`(取 token 与 repolish)。
2. `__init__` 中构建 nav+stack 的 `body` 之前,先建状态卡并加到最外层 `layout` 顶部:

```python
        status_card = QFrame()
        status_card.setProperty("class", "card")
        sv = QVBoxLayout(status_card)
        sv.setContentsMargins(14, 10, 14, 10)
        sv.setSpacing(2)
        self._status_badge = QLabel()
        sv.addWidget(self._status_badge)
        self._hotkey_line = QLabel()
        self._hotkey_line.setProperty("class", "muted")
        sv.addWidget(self._hotkey_line)
```

  并在最外层布局装配时把 `status_card` 放在 `body` 之前:`layout.addWidget(status_card)` 先于 `layout.addLayout(body, 1)`。
3. 初始化默认显示:`__init__` 末尾(`self._load()` 之后)加 `self.set_running_state("active"); self.refresh_hotkey_label()`。
4. 新增两方法:

```python
    _STATE_TEXT = {
        "active": ("● 使用中", theme.OK),
        "paused": ("● 已暂停(不控制鼠标)", theme.TEXT_MUTED),
        "permission": ("● 等待权限授权", theme.WARN),
        "error": ("● 摄像头异常", theme.DANGER),
    }

    def set_running_state(self, state: str) -> None:
        text, color = self._STATE_TEXT.get(state, self._STATE_TEXT["active"])
        self._status_badge.setText(text)
        self._status_badge.setStyleSheet(
            f"color: {color}; font-weight: 600; background: transparent;")

    def refresh_hotkey_label(self) -> None:
        key = format_hotkey(self._cfg.get("general/pause_hotkey"))
        self._hotkey_line.setText(f'切换快捷键:<b>{key}</b>(在"通用"页可修改)')
```

5. `_on_field_changed` 末尾(`_loading` 守卫之后、已处理 restart/light 之后)追加:

```python
        if key == "general/pause_hotkey":
            self.refresh_hotkey_label()
```

  (`_STATE_TEXT` 作为类属性放在方法区之前;`theme.OK` 等为字符串常量,类体求值安全。)

- [ ] **Step 3: app 同步**

现状(已核对):error 态由 `_start_vision` 里 `camera_error` 信号回调直接 `self._tray.set_state("error")` 触发,**不经** `_refresh_tray_state`;`_refresh_tray_state`(约 line 235)只判定 paused/permission/active 三态。为让四态都能同步到设置窗且不新增状态字段,引入统一同步入口 `_apply_state`,error 回调改走它。

`app.py`:
1. import 追加 `from sigtouch.interaction.hotkey import format_hotkey`。
2. 新增两方法(放在现 `_refresh_tray_state` 附近):

```python
    def _current_state(self) -> str:
        """常规三态(error 为瞬时态,由 camera_error 信号单独驱动)。"""
        if self._paused:
            return "paused"
        if not perms.all_granted():
            return "permission"
        return "active"

    def _apply_state(self, state: str) -> None:
        """统一把状态同步到托盘与设置窗(带人读快捷键)。"""
        hotkey = format_hotkey(self._cfg.get("general/pause_hotkey"))
        self._tray.set_state(state, hotkey)
        self._settings_dlg.set_running_state(state)
```

3. `_refresh_tray_state` 整体替换为:

```python
    def _refresh_tray_state(self) -> None:
        self._apply_state(self._current_state())
```

  (原函数体内的 paused/permission/active 判定已移入 `_current_state`;若原体是 `if self._paused: set_state("paused") elif ... else set_state("active")` 形式,逐一对应搬到 `_current_state` 的返回值即可,行为等价。)
4. `_start_vision` 里 camera_error 回调改为走统一入口:

```python
        self._vision.camera_error.connect(lambda _msg: self._apply_state("error"))
```

  (原 `lambda _msg: self._tray.set_state("error")` → 现在 error 也同步设置窗。)
5. 托盘"设置"菜单接线由 `self._settings_dlg.show` 改为 `self._show_settings`:

```python
    def _show_settings(self) -> None:
        self._settings_dlg.set_running_state(self._current_state())
        self._settings_dlg.refresh_hotkey_label()
        self._settings_dlg.show()
        self._settings_dlg.raise_()
```

  `__init__` 中 `self._tray.settings_requested.connect(self._settings_dlg.show)` 改为 `connect(self._show_settings)`。

`docs/manual-qa.md` 追加:

```markdown
15. (v1.5)状态与快捷键明示:打开设置窗顶部见状态条(使用中=绿点),按 Ctrl+Alt+P
    后托盘 tooltip 与设置状态条同步变为"已暂停"(灰点)、再按恢复;状态条第二行显示
    "切换快捷键:Ctrl+Alt+P";在通用页把快捷键改成别的组合,状态条第二行随即更新;
    托盘菜单切换项与 tooltip 也带该快捷键。
```

- [ ] **Step 4: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 115 + 4 = 119

```bash
git add sigtouch/ui/settings_dialog.py sigtouch/app.py docs/manual-qa.md \
        tests/test_settings_status.py tests/test_app_permissions.py
git commit -m "feat: settings status bar and app state sync for pause hotkey"
```

---

## 最终验收清单

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` 全部通过(预期 119)。
2. 分支推送后 CI 三平台全绿。
3. 人工 QA:`docs/manual-qa.md` 第 15 项。
4. 纯度 grep 与 PyQt grep 为空(`hotkey.py` 在 interaction/ 下须纯净)。
5. 切换键仍 Ctrl+Alt+P(`config.py` 默认值未改)。

## 后续工作(不在本计划)

- 图形化快捷键录制器;修饰键符号化(⌘⌥⇧);Overlay 状态提示。
