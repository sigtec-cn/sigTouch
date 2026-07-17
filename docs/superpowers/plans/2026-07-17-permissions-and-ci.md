# SigTouch v1.1 实现计划:权限引导与 CI 分发

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** macOS 权限引导 UI + 降级运行 + 自动激活(修复"启动即提示权限不足"),并新增 GitHub Actions 三平台构建与 Releases 分发。

**Architecture:** 重写 `platformsupport/permissions.py` 为三项权限(摄像头/辅助功能/输入监控)的统一 check/request/open_settings 接口(macOS 用 pyobjc+ctypes,其余平台恒授权,一律 fail-open);新增 `ui/permission_wizard.py` 引导窗(2s 轮询);`app.py` 改为降级状态机(Injector 与全局快捷键推迟到权限就绪才构造,就绪自动激活);两个 GitHub Actions workflow(CI 构建验证 + tag 触发 Release 分发)。

**Tech Stack:** 现有栈 + `pyobjc-framework-AVFoundation` / `pyobjc-framework-ApplicationServices`(仅 darwin);GitHub Actions(actions/checkout@v4, setup-python@v5, cache@v4, upload-artifact@v4, softprops/action-gh-release@v2)。

**Spec:** `docs/superpowers/specs/2026-07-17-permissions-and-ci-design.md`

## Global Constraints

- GUI 只能用 **PySide6**,严禁 PyQt6;项目 MIT。
- `sigtouch/interaction/`、`perception/types.py`、`perception/distance.py` 纯度约束不变(本计划不触碰这些目录)。
- 权限相关的任何异常都**不得**使应用启动失败或退出:检测失败 fail-open(视为已授权)并 `logging.warning`。
- 权限就绪后自动激活,**无需重启应用**。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`(当前基线 62 通过);提交信息 `feat:`/`fix:`/`test:`/`chore:`/`docs:` 前缀,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 可测试性:PermissionWizard 的 checker/requester/opener 依赖必须**调用时解析**(默认 None → 调用时取 `perms.snapshot` 等),不得在函数默认参数处绑定,否则 monkeypatch 失效。
- CI 产物:onedir 结构不变(LGPL);Release 资产命名 `SigTouch-<tag>-win64.zip` / `SigTouch-<tag>-macos-arm64.zip` / `SigTouch-<tag>-linux-x64.tar.gz`。

## 文件结构总览

```
sigtouch/platformsupport/permissions.py   # 重写(Task 1)
tests/test_permissions.py                 # 新增(Task 1)
tests/test_autostart.py                   # 修改:迁移旧 accessibility 测试(Task 1)
pyproject.toml                            # 修改:darwin-only pyobjc 依赖(Task 1)
sigtouch/ui/permission_wizard.py          # 新增(Task 2)
sigtouch/ui/icons.py  sigtouch/ui/tray.py # 修改:permission 态+菜单项(Task 2)
tests/test_permission_wizard.py           # 新增(Task 2)
sigtouch/app.py                           # 修改:降级状态机(Task 3)
tests/test_app_permissions.py             # 新增(Task 3)
tests/test_app_frame_path.py              # 修改:补 perms monkeypatch(Task 3)
.github/workflows/ci.yml                  # 新增(Task 4)
.github/workflows/release.yml             # 新增(Task 5)
README.md                                 # 新增(Task 5)
docs/manual-qa.md                         # 修改:权限流程走查(Task 5)
```

---

### Task 1: permissions 模块重写

**Files:**
- Modify: `sigtouch/platformsupport/permissions.py`(整体重写), `pyproject.toml`, `tests/test_autostart.py`
- Test: `tests/test_permissions.py`

**Interfaces:**
- Consumes: 无(叶子模块)。
- Produces: `PermissionKind`(CAMERA/ACCESSIBILITY/INPUT_MONITORING)、`check(kind) -> bool`、`request(kind) -> None`、`open_settings(kind) -> None`、`snapshot() -> dict[PermissionKind, bool]`、`all_granted() -> bool`。**删除** `accessibility_ok()`(app.py 的调用点由 Task 3 移除;本任务先在模块尾部保留一行兼容 shim `accessibility_ok = lambda: check(PermissionKind.ACCESSIBILITY)`,Task 3 删除)。

- [ ] **Step 1: pyproject 增加 darwin-only 依赖**

在 `[project].dependencies` 列表末尾追加两行:

```toml
    "pyobjc-framework-AVFoundation>=10.0; sys_platform == 'darwin'",
    "pyobjc-framework-ApplicationServices>=10.0; sys_platform == 'darwin'",
```

Run: `.venv/bin/pip install -e ".[dev]"`(安装新依赖)

- [ ] **Step 2: 写失败测试**

```python
# tests/test_permissions.py
import pytest

from sigtouch.platformsupport import permissions as P
from sigtouch.platformsupport.permissions import PermissionKind


def test_non_darwin_always_granted_and_noop(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "linux")
    for kind in PermissionKind:
        assert P.check(kind) is True
        P.request(kind)        # no-op,不抛
        P.open_settings(kind)  # no-op,不抛
    assert P.all_granted() is True


def test_snapshot_covers_all_kinds(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "linux")
    snap = P.snapshot()
    assert set(snap) == set(PermissionKind)
    assert all(snap.values())


def test_check_fails_open_on_darwin_errors(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "darwin")

    def boom(*a, **k):
        raise RuntimeError("api unavailable")

    monkeypatch.setattr(P, "_camera_status_darwin", boom)
    monkeypatch.setattr(P, "_accessibility_trusted_darwin", boom)
    monkeypatch.setattr(P, "_input_monitoring_status_darwin", boom)
    for kind in PermissionKind:
        assert P.check(kind) is True  # fail-open


def test_request_swallows_darwin_errors(monkeypatch):
    monkeypatch.setattr(P.sys, "platform", "darwin")

    def boom(*a, **k):
        raise RuntimeError("api unavailable")

    monkeypatch.setattr(P, "_camera_request_darwin", boom)
    monkeypatch.setattr(P, "_accessibility_trusted_darwin", boom)
    monkeypatch.setattr(P, "_input_monitoring_request_darwin", boom)
    for kind in PermissionKind:
        P.request(kind)  # 不抛


def test_settings_urls_cover_all_kinds():
    assert set(P._SETTINGS_URLS) == set(PermissionKind)
    for url in P._SETTINGS_URLS.values():
        assert url.startswith("x-apple.systempreferences:")


def test_real_host_check_returns_bool():
    # 真实宿主(macOS 走真实 API,其余平台恒 True)——接口契约冒烟
    for kind in PermissionKind:
        assert isinstance(P.check(kind), bool)
```

同时修改 `tests/test_autostart.py`:删除 `test_accessibility_ok_returns_bool`(该职责由上面的 `test_real_host_check_returns_bool` 接管;`from sigtouch.platformsupport import permissions` 的 import 若仅此测试使用则一并删除)。

- [ ] **Step 3: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_permissions.py -v`
Expected: FAIL(`ImportError: PermissionKind`)

- [ ] **Step 4: 重写 permissions.py**

```python
# sigtouch/platformsupport/permissions.py
"""三项系统权限的检测/请求/引导。仅 macOS 需要实际检测,其余平台恒为已授权。

所有检测与请求失败一律 fail-open(视为已授权)并记录日志——权限 API 在旧系统或
特殊环境上的异常不允许影响应用可用性。
"""
import logging
import sys
from enum import Enum, auto

_log = logging.getLogger(__name__)


class PermissionKind(Enum):
    CAMERA = auto()            # 摄像头采集(视觉管线)
    ACCESSIBILITY = auto()     # pynput 鼠标/键盘注入
    INPUT_MONITORING = auto()  # pynput GlobalHotKeys 全局快捷键


_SETTINGS_URLS = {
    PermissionKind.CAMERA:
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    PermissionKind.ACCESSIBILITY:
        "x-apple.systempreferences:com.apple.preference.security"
        "?Privacy_Accessibility",
    PermissionKind.INPUT_MONITORING:
        "x-apple.systempreferences:com.apple.preference.security"
        "?Privacy_ListenEvent",
}

_AV_AUTHORIZED = 3            # AVAuthorizationStatusAuthorized
_HID_REQUEST_LISTEN = 1       # kIOHIDRequestTypeListenEvent
_HID_ACCESS_GRANTED = 0       # kIOHIDAccessTypeGranted(1=denied, 2=unknown→未授权)


def check(kind: PermissionKind) -> bool:
    if sys.platform != "darwin":
        return True
    try:
        if kind is PermissionKind.CAMERA:
            return _camera_status_darwin()
        if kind is PermissionKind.ACCESSIBILITY:
            return _accessibility_trusted_darwin(prompt=False)
        return _input_monitoring_status_darwin()
    except Exception:
        _log.warning("权限检测失败,按已授权处理: %s", kind, exc_info=True)
        return True


def request(kind: PermissionKind) -> None:
    """触发系统授权弹窗。非 macOS no-op;失败仅记录。"""
    if sys.platform != "darwin":
        return
    try:
        if kind is PermissionKind.CAMERA:
            _camera_request_darwin()
        elif kind is PermissionKind.ACCESSIBILITY:
            _accessibility_trusted_darwin(prompt=True)
        else:
            _input_monitoring_request_darwin()
    except Exception:
        _log.warning("权限请求失败: %s", kind, exc_info=True)


def open_settings(kind: PermissionKind) -> None:
    """打开系统设置中对应的隐私面板。非 macOS no-op。"""
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(_SETTINGS_URLS[kind]))
    except Exception:
        _log.warning("打开系统设置失败: %s", kind, exc_info=True)


def snapshot() -> dict[PermissionKind, bool]:
    return {kind: check(kind) for kind in PermissionKind}


def all_granted() -> bool:
    return all(snapshot().values())


# ---- macOS 实现(懒导入;仅在 darwin 分支到达) ----

def _camera_status_darwin() -> bool:
    from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
    return status == _AV_AUTHORIZED  # NotDetermined/Denied 都视为未授权以便引导


def _camera_request_darwin() -> None:
    from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
    AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        AVMediaTypeVideo, lambda granted: None)


def _accessibility_trusted_darwin(prompt: bool) -> bool:
    from ApplicationServices import (AXIsProcessTrusted,
                                     AXIsProcessTrustedWithOptions,
                                     kAXTrustedCheckOptionPrompt)
    if prompt:
        return bool(AXIsProcessTrustedWithOptions(
            {kAXTrustedCheckOptionPrompt: True}))
    return bool(AXIsProcessTrusted())


def _iokit():
    import ctypes
    import ctypes.util
    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
    return lib, ctypes


def _input_monitoring_status_darwin() -> bool:
    lib, ctypes = _iokit()
    lib.IOHIDCheckAccess.restype = ctypes.c_int
    lib.IOHIDCheckAccess.argtypes = [ctypes.c_int]
    return lib.IOHIDCheckAccess(_HID_REQUEST_LISTEN) == _HID_ACCESS_GRANTED


def _input_monitoring_request_darwin() -> None:
    lib, ctypes = _iokit()
    lib.IOHIDRequestAccess.restype = ctypes.c_bool
    lib.IOHIDRequestAccess.argtypes = [ctypes.c_int]
    lib.IOHIDRequestAccess(_HID_REQUEST_LISTEN)


# Task 3 移除:app.py 迁移到 check() 前的兼容 shim
def accessibility_ok() -> bool:
    return check(PermissionKind.ACCESSIBILITY)
```

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`
Expected: 全部通过(62 - 1 删除 + 6 新增 = 67)

- [ ] **Step 6: 提交**

```bash
git add sigtouch/platformsupport/permissions.py pyproject.toml \
        tests/test_permissions.py tests/test_autostart.py
git commit -m "feat: unified three-permission check/request/open-settings module"
```

---

### Task 2: 权限引导窗与托盘 permission 态

**Files:**
- Create: `sigtouch/ui/permission_wizard.py`
- Modify: `sigtouch/ui/icons.py`, `sigtouch/ui/tray.py`
- Test: `tests/test_permission_wizard.py`

**Interfaces:**
- Consumes: `permissions` 模块(Task 1)。
- Produces:
  - `PermissionWizard(checker=None, requester=None, opener=None, parent=None)`(QDialog):三个依赖均为可空,**调用时**解析到 `perms.snapshot`/`perms.request`/`perms.open_settings`;信号 `all_granted`(仅在从"未全就绪"变"全就绪"的沿上发一次);方法 `refresh()`(测试直接驱动);内部 QTimer 每 2000ms 调 `refresh()`。
  - `icons.COLOR_PERMISSION = "#f1c40f"`。
  - `tray.TrayController` 新增信号 `permissions_requested`、菜单项"权限设置…"(位于"设置…"之后)、`set_state` 支持 `"permission"` 态(黄色图标,tooltip "SigTouch:等待权限授权",切换文案"暂停")。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_permission_wizard.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.platformsupport.permissions import PermissionKind as K


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _wizard(state, calls):
    from sigtouch.ui.permission_wizard import PermissionWizard
    return PermissionWizard(
        checker=lambda: dict(state),
        requester=lambda k: calls.append(("request", k)),
        opener=lambda k: calls.append(("open", k)))


def test_missing_permission_rendered_and_buttons_wired(qapp):
    state = {K.CAMERA: True, K.ACCESSIBILITY: False, K.INPUT_MONITORING: False}
    calls = []
    w = _wizard(state, calls)
    assert w._status_labels[K.CAMERA].text() == "✓"
    assert w._status_labels[K.ACCESSIBILITY].text() == "✗"
    assert w._request_buttons[K.CAMERA].isEnabled() is False   # 已授权→禁用
    assert w._request_buttons[K.ACCESSIBILITY].isEnabled() is True
    w._request_buttons[K.ACCESSIBILITY].click()
    w._open_buttons[K.INPUT_MONITORING].click()
    assert ("request", K.ACCESSIBILITY) in calls
    assert ("open", K.INPUT_MONITORING) in calls


def test_all_granted_emitted_once_on_rising_edge(qapp):
    state = {K.CAMERA: True, K.ACCESSIBILITY: False, K.INPUT_MONITORING: True}
    w = _wizard(state, [])
    got = []
    w.all_granted.connect(lambda: got.append(1))
    w.refresh()
    assert got == []                     # 未全就绪不发
    state[K.ACCESSIBILITY] = True
    w.refresh()
    assert got == [1]                    # 沿触发
    w.refresh()
    assert got == [1]                    # 不重复
    assert w._status_labels[K.ACCESSIBILITY].text() == "✓"


def test_tray_permission_state_and_menu(qapp):
    from sigtouch.ui.tray import TrayController
    t = TrayController()
    t.set_state("permission")            # 不抛即可(图标/文案人工核对)
    texts = [a.text() for a in t._menu.actions()]
    assert "权限设置…" in texts
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_permission_wizard.py -v`
Expected: FAIL(`ModuleNotFoundError: sigtouch.ui.permission_wizard`)

- [ ] **Step 3: 实现 permission_wizard.py**

```python
# sigtouch/ui/permission_wizard.py
"""权限引导窗:逐项状态 + 主动请求 + 打开系统设置,2s 自动轮询刷新。"""
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QGridLayout, QLabel, QPushButton,
                               QVBoxLayout)

from sigtouch.platformsupport import permissions as perms
from sigtouch.platformsupport.permissions import PermissionKind

_ROWS = [
    (PermissionKind.CAMERA, "摄像头", "识别手部与人脸(核心功能)"),
    (PermissionKind.ACCESSIBILITY, "辅助功能", "控制鼠标与键盘(手势注入)"),
    (PermissionKind.INPUT_MONITORING, "输入监控", "全局暂停快捷键"),
]
_POLL_MS = 2000
_CLOSE_DELAY_MS = 2000


class PermissionWizard(QDialog):
    all_granted = Signal()

    def __init__(self, checker=None, requester=None, opener=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 权限设置")
        # 依赖调用时解析,保证测试可注入、monkeypatch perms.* 也生效
        self._checker = checker
        self._requester = requester
        self._opener = opener
        self._was_all_granted = False
        self._status_labels: dict[PermissionKind, QLabel] = {}
        self._request_buttons: dict[PermissionKind, QPushButton] = {}
        self._open_buttons: dict[PermissionKind, QPushButton] = {}

        layout = QVBoxLayout(self)
        intro = QLabel("SigTouch 需要以下系统权限。授权后无需重启,应用会自动激活。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid = QGridLayout()
        for row, (kind, name, why) in enumerate(_ROWS):
            status = QLabel()
            self._status_labels[kind] = status
            grid.addWidget(status, row, 0)
            grid.addWidget(QLabel(f"<b>{name}</b> — {why}"), row, 1)
            req = QPushButton("请求权限")
            req.clicked.connect(lambda _=False, k=kind: self._request(k))
            self._request_buttons[kind] = req
            grid.addWidget(req, row, 2)
            opn = QPushButton("打开系统设置")
            opn.clicked.connect(lambda _=False, k=kind: self._open(k))
            self._open_buttons[kind] = opn
            grid.addWidget(opn, row, 3)
        layout.addLayout(grid)

        self._banner = QLabel("")
        layout.addWidget(self._banner)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(_POLL_MS)
        self.refresh()

    def _snapshot(self) -> dict:
        return self._checker() if self._checker else perms.snapshot()

    def _request(self, kind: PermissionKind) -> None:
        (self._requester or perms.request)(kind)

    def _open(self, kind: PermissionKind) -> None:
        (self._opener or perms.open_settings)(kind)

    def refresh(self) -> None:
        snap = self._snapshot()
        for kind, label in self._status_labels.items():
            ok = bool(snap.get(kind, True))
            label.setText("✓" if ok else "✗")
            label.setStyleSheet(
                f"color: {'#2ecc71' if ok else '#e74c3c'}; font-size: 18px;")
            self._request_buttons[kind].setEnabled(not ok)
        granted = all(snap.values())
        if granted and not self._was_all_granted:
            self._banner.setText("✓ 全部权限已就绪,SigTouch 已自动激活")
            self.all_granted.emit()
            QTimer.singleShot(_CLOSE_DELAY_MS, self.close)
        elif not granted:
            self._banner.setText("")
        self._was_all_granted = granted
```

- [ ] **Step 4: 修改 icons.py 与 tray.py**

`icons.py` 常量区追加:

```python
COLOR_PERMISSION = "#f1c40f"
```

`tray.py`:import 行加入 `COLOR_PERMISSION`;`_STATE_META` 追加:

```python
    "permission": (COLOR_PERMISSION, "SigTouch:等待权限授权", "暂停"),
```

`TrayController` 信号区追加 `permissions_requested = Signal()`;在"设置…"菜单项之后插入:

```python
        perms_action = QAction("权限设置…", menu)
        perms_action.triggered.connect(self.permissions_requested)
        menu.addAction(perms_action)
```

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`
Expected: 全部通过(67 + 3 = 70)

- [ ] **Step 6: 提交**

```bash
git add sigtouch/ui/permission_wizard.py sigtouch/ui/icons.py sigtouch/ui/tray.py \
        tests/test_permission_wizard.py
git commit -m "feat: permission wizard dialog and tray permission state"
```

---

### Task 3: app.py 降级状态机

**Files:**
- Modify: `sigtouch/app.py`, `sigtouch/platformsupport/permissions.py`(删除 shim), `tests/test_app_frame_path.py`
- Test: `tests/test_app_permissions.py`

**Interfaces:**
- Consumes: `permissions`(Task 1)、`PermissionWizard` / tray `permission` 态与 `permissions_requested` 信号(Task 2)。
- Produces: `SigTouchApp` 新行为——`self._injector: Injector | None`(仅辅助功能就绪才构造);`_ensure_capabilities()`(可重入按权限补齐能力);`_on_permissions_changed()`(激活+全就绪停轮询);`_show_wizard()`;`_refresh_tray_state()` 含 `permission` 态;`main()` 删除辅助功能 QMessageBox 块。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_app_permissions.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import sigtouch.app as app_module
from sigtouch.app import SigTouchApp
from sigtouch.config import Config
from sigtouch.perception.types import FrameResult
from sigtouch.platformsupport.permissions import PermissionKind as K
from tests.hand_fixtures import open_hand


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _VisionStub:
    def __init__(self):
        self.last_frame_monotonic_ms = 0

    def set_idle(self, b):
        pass

    def set_preview(self, b):
        pass

    def stop(self):
        pass

    def isRunning(self):
        return True


def _patch_perms(monkeypatch, state):
    monkeypatch.setattr(app_module.perms, "check", lambda k: state[k])
    monkeypatch.setattr(app_module.perms, "snapshot", lambda: dict(state))
    monkeypatch.setattr(app_module.perms, "all_granted",
                        lambda: all(state.values()))
    monkeypatch.setattr(app_module.perms, "request", lambda k: None)


def _make_app(monkeypatch):
    monkeypatch.setattr(
        SigTouchApp, "_start_vision",
        lambda self: setattr(self, "_vision", _VisionStub()))
    return SigTouchApp(Config(backend={}))


def test_degraded_start_never_constructs_injector(qapp, monkeypatch):
    state = {K.CAMERA: True, K.ACCESSIBILITY: False, K.INPUT_MONITORING: False}
    _patch_perms(monkeypatch, state)

    class BoomInjector:
        def __init__(self):
            raise AssertionError("缺辅助功能权限时不得构造 Injector")

    monkeypatch.setattr(app_module, "Injector", BoomInjector)
    a = _make_app(monkeypatch)
    assert a._injector is None
    assert a._hotkey_listener is None
    # 有手的帧:不注入、不崩,Overlay 正常收到手
    a._on_result(FrameResult(timestamp_ms=0, hand=open_hand(),
                             face_distance_m=0.6, face_present=True))
    assert a._overlay._hand is not None
    # 无手挂起帧:同样不崩
    a._on_result(FrameResult(timestamp_ms=5000, hand=None,
                             face_distance_m=0.6, face_present=False))


def test_capabilities_activate_after_grant_without_restart(qapp, monkeypatch):
    state = {K.CAMERA: True, K.ACCESSIBILITY: False, K.INPUT_MONITORING: False}
    _patch_perms(monkeypatch, state)
    created = []

    class FakeInjector:
        def __init__(self):
            created.append(self)

        def move(self, x, y):
            pass

        def dispatch(self, ev):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    hotkey_calls = []
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey",
                        lambda self: hotkey_calls.append(1))
    a = _make_app(monkeypatch)
    assert created == [] and hotkey_calls == []   # 降级期均未构造/启动
    assert a._perm_timer.isActive() is True        # 轮询已开启

    state[K.ACCESSIBILITY] = True
    state[K.INPUT_MONITORING] = True
    a._on_permissions_changed()
    assert len(created) == 1                       # 注入器已构造
    assert hotkey_calls == [1]                     # 快捷键已启动
    assert a._perm_timer.isActive() is False       # 全就绪停轮询


def test_full_permissions_start_is_unchanged(qapp, monkeypatch):
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
    assert isinstance(a._injector, FakeInjector)   # 直接完整启动
    assert a._perm_timer.isActive() is False       # 无需轮询
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_app_permissions.py -v`
Expected: FAIL(`SigTouchApp` 尚无 `_perm_timer`/降级逻辑)

- [ ] **Step 3: 修改 app.py**

新增 import:

```python
from sigtouch.platformsupport import permissions as perms
from sigtouch.platformsupport.permissions import PermissionKind
from sigtouch.ui.permission_wizard import PermissionWizard
```

`__init__` 全量替换为:

```python
    def __init__(self, cfg: Config, show_preview: bool = False):
        super().__init__()
        self._cfg = cfg
        self._paused = False
        self._injector: Injector | None = None   # 辅助功能就绪后才构造
        self._overlay = OverlayWindow(cfg)
        self._overlay.apply_screen()
        self._preview = PreviewWindow()
        self._settings_dlg = SettingsDialog(cfg)
        self._settings_dlg.settings_applied.connect(self._on_settings_applied)
        self._tray = TrayController(self)
        self._tray.toggle_requested.connect(self._toggle_pause)
        self._tray.settings_requested.connect(self._settings_dlg.show)
        self._tray.preview_requested.connect(self._show_preview)
        self._tray.quit_requested.connect(self._quit)
        self._tray.permissions_requested.connect(self._show_wizard)

        self._hotkey_bridge = _HotkeyBridge()
        self._hotkey_bridge.pressed.connect(self._toggle_pause)
        self._hotkey_listener = None

        self._wizard = PermissionWizard()
        self._wizard.all_granted.connect(self._on_permissions_changed)
        self._perm_timer = QTimer(self)
        self._perm_timer.timeout.connect(self._on_permissions_changed)

        self._ensure_capabilities()
        if not perms.all_granted():
            # 降级启动:引导窗 + 轮询;摄像头权限先主动触发系统首弹
            perms.request(PermissionKind.CAMERA)
            self._show_wizard()
            self._perm_timer.start(2000)

        self._build_interaction()
        self._vision: VisionThread | None = None
        self._start_vision()
        if show_preview:
            self._show_preview()
        self._refresh_tray_state()

        self._watchdog = QTimer(self)
        self._watchdog.timeout.connect(self._check_watchdog)
        self._watchdog.start(1000)
```

新增三个方法(放在 `_build_interaction` 之前):

```python
    def _ensure_capabilities(self) -> None:
        """按当前权限构造缺失能力;可重入,权限就绪即激活,无需重启。"""
        if self._injector is None and perms.check(PermissionKind.ACCESSIBILITY):
            self._injector = Injector()
        if self._hotkey_listener is None and \
                perms.check(PermissionKind.INPUT_MONITORING):
            self._setup_hotkey()

    def _on_permissions_changed(self) -> None:
        self._ensure_capabilities()
        if perms.all_granted():
            self._perm_timer.stop()
        self._refresh_tray_state()

    def _show_wizard(self) -> None:
        self._wizard.show()
        self._wizard.raise_()
```

`_refresh_tray_state` 替换为:

```python
    def _refresh_tray_state(self) -> None:
        if self._paused:
            self._tray.set_state("paused")
        elif not perms.all_granted():
            self._tray.set_state("permission")
        else:
            self._tray.set_state("active")
```

`_setup_hotkey` 开头(停止旧 listener 的代码之后、读取 combo 之前)插入门控:

```python
        if not perms.check(PermissionKind.INPUT_MONITORING):
            return  # 输入监控未授权:跳过,权限就绪后由 _ensure_capabilities 再启动
```

`_on_result` 中所有 `self._injector.X` 调用点改为判空守卫(注入跳过,Overlay/状态机照常),完整替换后的方法:

```python
    def _on_result(self, result) -> None:
        self._preview.update_result(result)
        suspended = self._gate.update(result.face_present, result.timestamp_ms)
        if self._paused or suspended:
            for ev in self._machine.update(None, result.timestamp_ms):
                if self._injector is not None:
                    self._injector.dispatch(ev)
            if self._injector is not None:
                self._injector.release_all()
            self._overlay.clear()
            self._vision.set_idle(True)
            return
        self._vision.set_idle(False)

        events = self._machine.update(result.hand, result.timestamp_ms)
        if result.hand is not None:
            x, y = self._mapper.update(F.anchor_point(result.hand),
                                       self._machine.pinching,
                                       result.timestamp_ms)
            if self._injector is not None:
                self._injector.move(x + self._screen_origin[0],
                                    y + self._screen_origin[1])
            dist = result.face_distance_m if result.face_distance_m else 0.6
            scale = overlay_scale(dist,
                                  self._cfg.get("display/screen_diag_inch"))
            self._overlay.update_hand(result.hand, scale, self._machine.feedback)
        else:
            self._overlay.clear()
        for ev in events:
            if self._injector is not None:
                self._injector.dispatch(ev)
```

`_toggle_pause` / `_on_settings_applied` / `_quit` 中的 `self._injector.release_all()` 一律改为:

```python
        if self._injector is not None:
            self._injector.release_all()
```

`main()` 中删除整段辅助功能提示(`from sigtouch.platformsupport.permissions import accessibility_ok` 起到 `QMessageBox.warning(...)` 止);模型检查保留。
`permissions.py` 末尾删除 `accessibility_ok` shim。

- [ ] **Step 4: 更新 tests/test_app_frame_path.py**

该文件现有测试构造 `SigTouchApp` 前须授予全部权限,否则在真实 mac 宿主上 `check(ACCESSIBILITY)` 为 False 会使 `_injector` 为 None 而破坏断言。在文件顶部加入:

```python
from sigtouch.platformsupport.permissions import PermissionKind


def _grant_all(monkeypatch):
    import sigtouch.app as app_module
    monkeypatch.setattr(app_module.perms, "check", lambda k: True)
    monkeypatch.setattr(app_module.perms, "snapshot",
                        lambda: {k: True for k in PermissionKind})
    monkeypatch.setattr(app_module.perms, "all_granted", lambda: True)
    monkeypatch.setattr(app_module.perms, "request", lambda k: None)
```

并在每个测试构造 `SigTouchApp` 之前调用 `_grant_all(monkeypatch)`(按该文件现有结构接入;不得改动既有断言)。

- [ ] **Step 5: 运行确认通过 + 全量回归**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`
Expected: 全部通过(70 + 3 = 73)

- [ ] **Step 6: 提交**

```bash
git add sigtouch/app.py sigtouch/platformsupport/permissions.py \
        tests/test_app_permissions.py tests/test_app_frame_path.py
git commit -m "feat: degraded startup with permission gating and auto-activation"
```

---

### Task 4: CI 工作流

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: 现有 `pyproject.toml` / `scripts/download_models.py` / `packaging/sigtouch.spec` / 测试套件。
- Produces: push/PR → main 时三平台构建+测试+产物 artifact;Task 5 的 release.yml 复用相同步骤结构。

- [ ] **Step 1: 写 ci.yml**

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    env:
      QT_QPA_PLATFORM: offscreen
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install Linux Qt runtime deps
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 \
            libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
            libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-cursor0
      - name: Install project
        run: pip install -e ".[dev]"
      - name: Cache MediaPipe models
        uses: actions/cache@v4
        with:
          path: sigtouch/models
          key: mediapipe-models-${{ hashFiles('scripts/download_models.py') }}
      - name: Download models
        run: python scripts/download_models.py
      - name: Run tests
        run: python -m pytest tests/ -v
      - name: Build (PyInstaller onedir)
        run: pyinstaller packaging/sigtouch.spec
      - uses: actions/upload-artifact@v4
        with:
          name: SigTouch-${{ runner.os }}
          path: dist/SigTouch/
          retention-days: 7
```

- [ ] **Step 2: 本地校验 YAML 语法**

Run: `.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('yaml ok')"`
(若 venv 无 pyyaml:`.venv/bin/pip install pyyaml` 后再跑)
Expected: `yaml ok`

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/ci.yml
git commit -m "chore: three-platform CI build/test/package workflow"
```

真实运行验证在 Task 5 完成后随分支推送一并进行(见最终验收)。

---

### Task 5: Release 工作流、README 与手动 QA 更新

**Files:**
- Create: `.github/workflows/release.yml`, `README.md`
- Modify: `docs/manual-qa.md`

**Interfaces:**
- Consumes: ci.yml 的步骤结构(Task 4)。
- Produces: tag `v*` → GitHub Release 挂三平台资产;README 为用户下载/安装/权限入口文档。

- [ ] **Step 1: 写 release.yml**

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  build-and-release:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    env:
      QT_QPA_PLATFORM: offscreen
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Install Linux Qt runtime deps
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 \
            libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
            libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-cursor0
      - name: Install project
        run: pip install -e ".[dev]"
      - name: Cache MediaPipe models
        uses: actions/cache@v4
        with:
          path: sigtouch/models
          key: mediapipe-models-${{ hashFiles('scripts/download_models.py') }}
      - name: Download models
        run: python scripts/download_models.py
      - name: Run tests
        run: python -m pytest tests/ -v
      - name: Build (PyInstaller onedir)
        run: pyinstaller packaging/sigtouch.spec
      - name: Package (Windows)
        if: runner.os == 'Windows'
        run: Compress-Archive -Path dist/SigTouch -DestinationPath SigTouch-${{ github.ref_name }}-win64.zip
      - name: Package (macOS)
        if: runner.os == 'macOS'
        run: cd dist && zip -qry ../SigTouch-${{ github.ref_name }}-macos-arm64.zip SigTouch
      - name: Package (Linux)
        if: runner.os == 'Linux'
        run: tar -czf SigTouch-${{ github.ref_name }}-linux-x64.tar.gz -C dist SigTouch
      - uses: softprops/action-gh-release@v2
        with:
          files: |
            SigTouch-*.zip
            SigTouch-*.tar.gz
          generate_release_notes: true
```

- [ ] **Step 2: 写 README.md(仓库根,当前缺失)**

````markdown
# SigTouch

用摄像头把你的手变成鼠标:MediaPipe 识别手部与人眼,半透明手部轮廓投影到屏幕
(Oculus 风格,随人-屏距离自适应缩放),手势完成点击 / 拖拽 / 滚动 / 回车 / 退格。
常驻系统托盘,支持 Windows / macOS / Linux。MIT 协议。

## 手势

| 手势 | 动作 |
|---|---|
| 拇指+食指快捻 | 左键单击(捻住移动=拖拽) |
| 拇指+中指快捻 | 右键单击 |
| 三指捻住上下移动 | 滚动 |
| OK 手势保持 0.5s | 回车 |
| 张开手掌前推 | 退格 |
| Ctrl+Alt+P | 暂停/恢复 |

## 下载安装

从 [Releases](../../releases) 下载对应平台压缩包,解压后运行 `SigTouch`:

- **Windows**:解压 `SigTouch-*-win64.zip`,运行 `SigTouch\SigTouch.exe`。
- **macOS**:解压 `SigTouch-*-macos-arm64.zip`;产物未签名,首次运行前需解除隔离:
  `xattr -cr SigTouch`,然后运行 `SigTouch/SigTouch`。启动后按权限引导窗逐项授权
  摄像头、辅助功能、输入监控(授权后自动激活,无需重启)。
- **Linux (X11)**:解压 `SigTouch-*-linux-x64.tar.gz`,运行 `SigTouch/SigTouch`。
  Wayland 下输入注入受限(已知限制)。

## 开发

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python scripts/download_models.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v
.venv/bin/python -m sigtouch --preview   # 带调试预览窗启动
```

打包:`pyinstaller packaging/sigtouch.spec`(详见 `packaging/README.md`);
设计文档见 `docs/superpowers/specs/`,手动 QA 清单见 `docs/manual-qa.md`。
````

- [ ] **Step 3: manual-qa.md 追加权限流程走查**

在清单末尾追加:

```markdown
11. (macOS)全新授权流程:撤销/未授权状态下启动 → 弹权限引导窗,托盘黄色"等待
    权限授权";逐项 [请求权限]/[打开系统设置] 完成摄像头、辅助功能、输入监控授权,
    每项授权后 2s 内向导状态变 ✓;全部就绪后向导自动关闭、托盘转绿、注入与全局
    快捷键即时生效——全程不重启应用。托盘菜单"权限设置…"可随时重新打开向导。
```

- [ ] **Step 4: 校验 + 提交**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"`
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q`(回归不受影响)

```bash
git add .github/workflows/release.yml README.md docs/manual-qa.md
git commit -m "docs: release workflow, user README and permission-flow QA item"
```

---

## 最终验收清单

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` 全部通过(预期 73)。
2. 分支推送后 GitHub Actions CI 在三平台全绿(真实运行验证)。
3. 人工 QA(macOS,真机):`docs/manual-qa.md` 第 11 项权限流程走查通过——启动不退出、引导可用、授权后自动激活。
4. 打 tag `v0.1.0` 后 Release 自动创建并挂载三平台资产(可在人工 QA 通过后执行)。
5. `grep -ri "PyQt" sigtouch/` 无结果;纯度 grep(interaction/types/distance)无结果(约束不变)。

## 后续工作(不在本计划)

- macOS 代码签名与公证;Windows Inno 安装器;Linux AppImage。
- 权限运行中被撤销的实时降级。
- Intel macOS(macos-13)构建矩阵。

