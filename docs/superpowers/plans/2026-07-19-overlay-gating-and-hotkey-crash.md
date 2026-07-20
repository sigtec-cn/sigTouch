# SigTouch v1.6 实现计划:置顶门控、Dock 收起与授权闪退防御

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅启动态(active)保持 Overlay 置顶,其余状态降层并隐藏;macOS 隐藏 Dock 图标(LSUIElement)+ 关窗收起契约固化;输入监控权限运行中授予时不抢建监听器,向导提示重启并提供重启按钮。

**Architecture:** native 加 `unpin_window_topmost`(与 pin 对称、同 cocoa 门控)→ overlay 加幂等 `set_topmost(bool)` → app 由 `_apply_state` 单一入口驱动置顶 + `_im_granted_at_start`/`_hotkey_needs_restart` 防御 + `_restart_app`;wizard 加重启提示行与 `restart_requested` 信号;打包加 LSUIElement。

**Spec:** `docs/superpowers/specs/2026-07-19-overlay-gating-and-hotkey-crash-design.md`

## Global Constraints

- `pin/unpin_window_topmost` 必须保持 `QGuiApplication.platformName() == "cocoa"` 门控(offscreen 下 winId 占位句柄喂 objc 会段错误——v1.2 已知);fail-open。
- `_apply_state` 仍是 UI 状态唯一入口(v1.5 不变式);`set_topmost` 幂等。
- **语义变更(有意)**:v1.1 的"运行中授予输入监控即启动快捷键"改为"置 `_hotkey_needs_restart`,重启后生效"——`tests/test_app_permissions.py::test_capabilities_activate_after_grant_without_restart` 的 hotkey 断言须随语义更新(injector 部分不变);这是本计划明确要求的测试修改,不是回归。
- 启动时已有输入监控权限 → 行为与现在完全一致(直接启动监听器)。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`(基线 124);提交前缀规范同前,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 文件结构总览

```
sigtouch/ui/native.py                # unpin_window_topmost(Task 1)
sigtouch/ui/overlay.py               # set_topmost(Task 1)
tests/test_overlay_topmost.py        # 新增(Task 1)
sigtouch/ui/permission_wizard.py     # 重启提示行 + restart_requested(Task 2)
tests/test_permission_wizard.py      # 追加(Task 2)
sigtouch/app.py                      # 置顶门控 + 闪退防御 + _restart_app(Task 3)
tests/test_app_permissions.py        # 语义更新 + 新增(Task 3)
packaging/sigtouch.spec              # LSUIElement(Task 4)
tests/test_window_close_contract.py  # 新增(Task 4)
docs/manual-qa.md                    # 第 16 项(Task 4)
```

---

### Task 1: native unpin 与 overlay set_topmost

**Files:**
- Modify: `sigtouch/ui/native.py`, `sigtouch/ui/overlay.py`
- Test: `tests/test_overlay_topmost.py`

**Interfaces:**
- Produces: `native.unpin_window_topmost(widget)`(darwin 下 `setLevel_(0)` + `setCollectionBehavior_(0)`,cocoa 门控与 fail-open 结构照抄现有 pin);`OverlayWindow.set_topmost(enabled: bool)`(True→show+pin;False→unpin+hide;幂等,内部 `_topmost` 标志,`__init__` 初始化为 False)。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_overlay_topmost.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_set_topmost_gates_visibility_and_pin(qapp, monkeypatch):
    import sigtouch.ui.overlay as ov
    pins, unpins = [], []
    monkeypatch.setattr(ov, "pin_window_topmost", lambda w: pins.append(1))
    monkeypatch.setattr(ov, "unpin_window_topmost", lambda w: unpins.append(1))
    w = ov.OverlayWindow(Config(backend={}))
    w.set_topmost(True)
    assert w.isVisible() and pins == [1]
    w.set_topmost(True)
    assert pins == [1]                       # 幂等:重复 True 不重复 pin
    w.set_topmost(False)
    assert not w.isVisible() and unpins == [1]
    w.set_topmost(False)
    assert unpins == [1]                     # 幂等:重复 False 不重复 unpin


def test_unpin_noop_non_darwin(monkeypatch):
    from sigtouch.ui import native
    monkeypatch.setattr(native.sys, "platform", "linux")
    native.unpin_window_topmost(object())    # 非 darwin no-op,不抛


def test_unpin_fails_open_on_error(monkeypatch, qapp):
    from sigtouch.ui import native
    monkeypatch.setattr(native.sys, "platform", "darwin")
    # offscreen 平台名非 cocoa → 门控直接返回,不触碰 objc,不抛
    native.unpin_window_topmost(object())
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_overlay_topmost.py -v`
Expected: FAIL(无 set_topmost / unpin_window_topmost)

- [ ] **Step 2: 实现**

`native.py` 末尾追加(**先读现有 `pin_window_topmost`,门控与异常结构逐行对齐**):

```python
_NORMAL_LEVEL = 0  # NSNormalWindowLevel


def unpin_window_topmost(widget) -> None:
    """把窗口降回普通层级(与 pin_window_topmost 对称)。仅 macOS 有实际动作。"""
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.platformName() != "cocoa":
            return  # offscreen/headless:winId 是占位句柄,喂给 objc 会段错误
        import objc
        from ctypes import c_void_p

        ns_view = objc.objc_object(c_void_p=c_void_p(int(widget.winId())))
        ns_window = ns_view.window()
        if ns_window is None:
            return
        ns_window.setLevel_(_NORMAL_LEVEL)
        ns_window.setCollectionBehavior_(0)
    except Exception:
        _log.warning("恢复普通窗口层级失败,保持当前层级", exc_info=True)
```

(若现有 pin 的 cocoa 门控写法与上稍异,以现有 pin 为准逐行对齐。)

`overlay.py`:import 行把 `pin_window_topmost` 扩为 `pin_window_topmost, unpin_window_topmost`;`__init__` 加 `self._topmost = False`;新增方法:

```python
    def set_topmost(self, enabled: bool) -> None:
        """启动态置顶显示;非启动态降层并隐藏,彻底不干扰其他窗口。幂等。"""
        if enabled == self._topmost:
            return
        self._topmost = enabled
        if enabled:
            self.show()
            pin_window_topmost(self)
        else:
            unpin_window_topmost(self)
            self.hide()
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 124 + 3 = 127

```bash
git add sigtouch/ui/native.py sigtouch/ui/overlay.py tests/test_overlay_topmost.py
git commit -m "feat: symmetric window unpin and idempotent overlay topmost toggle"
```

---

### Task 2: 向导重启提示与信号

**Files:**
- Modify: `sigtouch/ui/permission_wizard.py`
- Test: `tests/test_permission_wizard.py`(追加)

**Interfaces:**
- Produces: `PermissionWizard(..., restart_hint=None)`(可空回调,调用时解析);信号 `restart_requested`;属性 `_restart_row`(QFrame,默认隐藏,`refresh()` 时按 `restart_hint()` 显隐)。既有行为契约(升沿/timer/注入)不变。

- [ ] **Step 1: 写失败测试(追加)**

```python
def test_restart_hint_row_and_signal(qapp):
    from sigtouch.ui.permission_wizard import PermissionWizard
    state = {K.CAMERA: True, K.ACCESSIBILITY: True, K.INPUT_MONITORING: True}
    flag = {"v": False}
    w = PermissionWizard(checker=lambda: dict(state),
                         requester=lambda k: None, opener=lambda k: None,
                         restart_hint=lambda: flag["v"])
    assert w._restart_row.isVisibleTo(w) is False   # 默认隐藏
    flag["v"] = True
    w.refresh()
    assert w._restart_row.isVisibleTo(w) is True    # 提示出现
    got = []
    w.restart_requested.connect(lambda: got.append(1))
    w._restart_button.click()
    assert got == [1]
    flag["v"] = False
    w.refresh()
    assert w._restart_row.isVisibleTo(w) is False


def test_wizard_without_restart_hint_backward_compatible(qapp):
    from sigtouch.ui.permission_wizard import PermissionWizard
    w = PermissionWizard(checker=lambda: {k: True for k in K},
                         requester=lambda k: None, opener=lambda k: None)
    w.refresh()
    assert w._restart_row.isVisibleTo(w) is False   # 无 hint 恒隐藏
```

(用 `isVisibleTo(w)` 而非 `isVisible()`——offscreen 下父窗未 show 时后者恒 False,前者反映 setVisible 意图。)

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_permission_wizard.py -v`
Expected: FAIL(构造不接受 restart_hint)

- [ ] **Step 2: 实现**

`permission_wizard.py`:
1. `__init__` 签名加 `restart_hint=None`(在 `parent=None` 之前),存 `self._restart_hint = restart_hint`;信号区加 `restart_requested = Signal()`。
2. 卡片循环之后、`layout.addStretch(1)` 之前插入:

```python
        self._restart_row = QFrame()
        self._restart_row.setProperty("class", "card")
        rl = QHBoxLayout(self._restart_row)
        rl.setContentsMargins(14, 8, 14, 8)
        warn = QLabel("⚠️ 快捷键需重启应用后生效")
        rl.addWidget(warn)
        rl.addStretch(1)
        self._restart_button = QPushButton("重启应用")
        self._restart_button.setProperty("class", "primary")
        self._restart_button.clicked.connect(self.restart_requested)
        rl.addWidget(self._restart_button)
        self._restart_row.setVisible(False)
        layout.addWidget(self._restart_row)
```

3. `refresh()` 末尾(`self._was_all_granted = granted` 之前或之后均可,但要每次刷新执行)追加:

```python
        needs_restart = bool(self._restart_hint()) if self._restart_hint else False
        self._restart_row.setVisible(needs_restart)
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 127 + 2 = 129

```bash
git add sigtouch/ui/permission_wizard.py tests/test_permission_wizard.py
git commit -m "feat: wizard restart hint row and restart signal"
```

---

### Task 3: app 接线(置顶门控 + 闪退防御 + 重启)

**Files:**
- Modify: `sigtouch/app.py`, `tests/test_app_permissions.py`

**Interfaces:**
- Produces: `_apply_state` 追加 `self._overlay.set_topmost(state == "active")`;watchdog raise 仅 active;`self._im_granted_at_start: bool`、`self._hotkey_needs_restart: bool`;`_ensure_capabilities` 防御分支;`_restart_app()`;wizard 构造传 `restart_hint`、连接 `restart_requested`。

- [ ] **Step 1: 更新语义变更测试 + 写新失败测试**

`tests/test_app_permissions.py`:

1. `test_capabilities_activate_after_grant_without_restart` 中 hotkey 断言按新语义更新:授予后 `hotkey_calls == []` 且 `a._hotkey_needs_restart is True`(injector 断言 `len(created) == 1` 不变;测试名可改为 `test_capabilities_activate_after_grant_hotkey_deferred`)。同理检查 `test_wizard_rising_edge_activates_app` 若含 hotkey 断言一并更新(仅 injector/timer 断言保留)。

2. 追加:

```python
def test_hotkey_started_when_granted_at_launch(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    calls = []
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey",
                        lambda self: calls.append(1))
    a = _make_app(monkeypatch)
    assert calls == [1]                      # 启动即有权限 → 正常启动监听
    assert a._hotkey_needs_restart is False


def test_apply_state_gates_overlay_topmost(qapp, monkeypatch):
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
    seen = []
    monkeypatch.setattr(a._overlay, "set_topmost", lambda e: seen.append(e))
    a._apply_state("active")
    a._apply_state("paused")
    a._apply_state("permission")
    a._apply_state("error")
    assert seen == [True, False, False, False]


def test_watchdog_raise_only_when_active(qapp, monkeypatch):
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
    raises = []
    monkeypatch.setattr(a._overlay, "isVisible", lambda: True)
    monkeypatch.setattr(a._overlay, "raise_", lambda: raises.append(1))
    a._ui_state = "paused"
    a._check_watchdog()
    assert raises == []
    a._ui_state = "active"
    a._check_watchdog()
    assert raises == [1]


def test_restart_app_spawns_then_quits(qapp, monkeypatch):
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
    spawned, quits = [], []
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda cmd: spawned.append(cmd))
    monkeypatch.setattr(a, "_quit", lambda: quits.append(1))
    a._restart_app()
    assert spawned and spawned[0][-2:] == ["-m", "sigtouch"]  # 非冻结命令形态
    assert quits == [1]
    # 拉起失败 → 不退出
    def boom(cmd):
        raise OSError("spawn failed")
    monkeypatch.setattr(subprocess, "Popen", boom)
    a._restart_app()
    assert quits == [1]                       # 未再退出
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_app_permissions.py -v`
Expected: FAIL(无 _hotkey_needs_restart / set_topmost 未接 / _restart_app 缺失)

- [ ] **Step 2: 修改 app.py**

1. import 区补 `import subprocess`(模块顶,与现有 import 风格一致)。
2. `__init__`:`self._hotkey_listener = None` 之后加:

```python
        self._im_granted_at_start = perms.check(PermissionKind.INPUT_MONITORING)
        self._hotkey_needs_restart = False
```

3. wizard 构造改为 `PermissionWizard(restart_hint=lambda: self._hotkey_needs_restart)`;其后加 `self._wizard.restart_requested.connect(self._restart_app)`。
4. `_ensure_capabilities` 的 hotkey 分支替换为:

```python
        if self._hotkey_listener is None and \
                perms.check(PermissionKind.INPUT_MONITORING):
            if self._im_granted_at_start:
                self._setup_hotkey()
            else:
                # 运行中才授予:不抢建 event tap——TCC 切换窗口内系统可能终止进程,
                # 且 macOS 要求重启应用权限才真正生效
                self._hotkey_needs_restart = True
```

5. `_apply_state` 末尾追加 `self._overlay.set_topmost(state == "active")`。
6. `_check_watchdog` 的 raise 块改为:

```python
        if self._ui_state == "active" and self._overlay.isVisible():
            self._overlay.raise_()
```

7. 新增方法:

```python
    def _restart_app(self) -> None:
        """重启自身(输入监控权限需重启生效)。拉起失败仅记录,不退出。"""
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable]
            else:
                cmd = [sys.executable, "-m", "sigtouch"]
            subprocess.Popen(cmd)
        except Exception:
            _log.warning("自动重启失败,请手动重启应用", exc_info=True)
            return
        self._quit()
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 129 + 4 = 133(语义更新的既有测试不计新增)

```bash
git add sigtouch/app.py tests/test_app_permissions.py
git commit -m "feat: gate overlay topmost by state and defer hotkey until restart"
```

---

### Task 4: LSUIElement、关窗契约与文档

**Files:**
- Modify: `packaging/sigtouch.spec`, `docs/manual-qa.md`
- Test: `tests/test_window_close_contract.py`(新增)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_window_close_contract.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config
from sigtouch.platformsupport.permissions import PermissionKind as K


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def test_settings_close_hides_but_app_survives(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(Config(backend={}))
    dlg.show()
    assert dlg.isVisible()
    dlg.close()
    assert not dlg.isVisible()               # 关窗=收起
    assert QApplication.instance() is not None


def test_wizard_close_hides_but_app_survives(qapp):
    from sigtouch.ui.permission_wizard import PermissionWizard
    w = PermissionWizard(checker=lambda: {k: True for k in K},
                         requester=lambda k: None, opener=lambda k: None)
    w.show()
    w.close()
    assert not w.isVisible()
    assert QApplication.instance() is not None
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_window_close_contract.py -v`
Expected: PASS 或 FAIL——若直接 PASS(契约本就成立),仍保留为回归护栏,继续 Step 2。

- [ ] **Step 2: spec 加 LSUIElement + 构建验证**

`packaging/sigtouch.spec` 的 `BUNDLE(info_plist={...})` 增加一行:

```python
        "LSUIElement": True,
```

Run: `rm -rf build dist && .venv/bin/pyinstaller packaging/sigtouch.spec`
Expected: 构建成功;`plutil -p dist/SigTouch.app/Contents/Info.plist | grep -i LSUIElement` 显示 1/true。

- [ ] **Step 3: manual-qa 第 16 项**

```markdown
16. (v1.6)置顶门控与收起走查:按 Ctrl+Alt+P 暂停后影子消失且不再压住任何窗口,恢复后
    影子回到最上层(含全屏应用);Dock 无 SigTouch 图标、Cmd-Tab 无条目,设置/权限窗
    经托盘菜单唤起,点关闭仅收起、托盘继续运行;在系统设置勾选"输入监控"权限**不再
    闪退**,权限向导出现"快捷键需重启应用后生效"提示,点"重启应用"后应用自动重启且
    Ctrl+Alt+P 生效;启动时已有全部权限的正常启动不受影响。
```

- [ ] **Step 4: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q` → 133 + 2 = 135

```bash
git add packaging/sigtouch.spec docs/manual-qa.md tests/test_window_close_contract.py
git commit -m "feat: hide dock icon and pin window-close-to-tray contract"
```

---

## 最终验收清单

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` 全部通过(预期 135)。
2. 分支推送后 CI 三平台全绿。
3. 本地 .app 构建含 LSUIElement(Task 4 Step 2)。
4. 人工 QA:`docs/manual-qa.md` 第 16 项(重点:勾选输入监控不再闪退)。
5. 纯度 grep 与 PyQt grep 为空。

## 后续工作(不在本计划)

- 闪退根因的 log show 实证(用户侧执行,已在 spec §2 给出命令;修复对两种根因均有效)。
- 权限授予后免重启启用快捷键(macOS 限制,不可行)。
