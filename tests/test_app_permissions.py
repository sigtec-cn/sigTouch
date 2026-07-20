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


def test_capabilities_activate_after_grant_hotkey_deferred(qapp, monkeypatch):
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
    assert hotkey_calls == []                      # 运行中授予:快捷键推迟到重启
    assert a._hotkey_needs_restart is True
    assert a._perm_timer.isActive() is False       # 全就绪停轮询


def test_wizard_rising_edge_activates_app(qapp, monkeypatch):
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

    state[K.ACCESSIBILITY] = True
    state[K.INPUT_MONITORING] = True
    a._wizard.refresh()                            # 经向导信号路径,而非直接调用
    assert len(created) == 1
    assert a._perm_timer.isActive() is False


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


def test_overlay_receives_mapper_cursor(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            self.moves = []

        def move(self, x, y):
            self.moves.append((x, y))

        def dispatch(self, ev):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    a = _make_app(monkeypatch)
    calls = []
    monkeypatch.setattr(
        a._overlay, "update_hand",
        lambda hand, scale, feedback, cursor_px=None: calls.append(cursor_px))
    a._on_result(FrameResult(timestamp_ms=0, hand=open_hand(),
                             face_distance_m=0.6, face_present=True))
    assert calls and calls[0] is not None
    ox, oy = a._screen_origin
    assert a._injector.moves[0] == (calls[0][0] + ox, calls[0][1] + oy)


def test_light_settings_do_not_restart_vision(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    monkeypatch.setattr(
        "sigtouch.platformsupport.autostart.set_autostart", lambda *_: None)
    a = _make_app(monkeypatch)
    restarts = []
    monkeypatch.setattr(a, "_restart_vision", lambda: restarts.append(1))
    a._apply_light_settings()
    assert restarts == []            # 轻量路径不重启视觉线程
    a._on_vision_restart_needed()
    assert restarts == [1]           # 重启路径走 _restart_vision


def test_overlay_scale_consumes_offset_and_multiplier(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            pass

        def move(self, x, y):
            pass

        def dispatch(self, ev):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    monkeypatch.setattr(
        SigTouchApp, "_start_vision",
        lambda self: setattr(self, "_vision", _VisionStub()))
    from sigtouch.config import Config as _Config
    cfg = _Config(backend={"display/hand_scale_multiplier": 2.0})
    a = SigTouchApp(cfg)
    scales = []
    monkeypatch.setattr(
        a._overlay, "update_hand",
        lambda hand, scale, feedback, cursor_px=None: scales.append(scale))
    a._on_result(FrameResult(timestamp_ms=0, hand=open_hand(),
                             face_distance_m=0.6, face_present=True))
    assert scales and scales[0] == pytest.approx(2.0)  # 0.6m/24吋 基准 1.0 × 倍率 2.0


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


def test_hotkey_change_refreshes_tray(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self): pass
        def release_all(self): pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    monkeypatch.setattr("sigtouch.platformsupport.autostart.set_autostart", lambda *_: None)
    a = _make_app(monkeypatch)
    calls = []
    monkeypatch.setattr(a._tray, "set_state", lambda s, hk="": calls.append((s, hk)))
    a._cfg.set("general/pause_hotkey", "<cmd>+<shift>+s")
    a._apply_light_settings()
    assert calls and calls[-1][1] == "Cmd+Shift+S"


def test_show_settings_uses_ui_state_not_recomputed(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self): pass
        def release_all(self): pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    a = _make_app(monkeypatch)
    a._apply_state("error")               # 摄像头错误态
    seen = []
    monkeypatch.setattr(a._settings_dlg, "set_running_state", lambda s: seen.append(s))
    monkeypatch.setattr(a._settings_dlg, "show", lambda: None)
    monkeypatch.setattr(a._settings_dlg, "raise_", lambda: None)
    a._show_settings()
    assert seen == ["error"]              # 打开设置沿用 _ui_state,不回退成 active


def test_blank_hotkey_no_tray_suffix(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self): pass
        def release_all(self): pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    a = _make_app(monkeypatch)
    calls = []
    monkeypatch.setattr(a._tray, "set_state", lambda s, hk="": calls.append((s, hk)))
    a._cfg.set("general/pause_hotkey", "")
    a._apply_state("active")
    assert calls[-1] == ("active", "")    # 空快捷键不带后缀


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


def test_light_settings_cannot_bypass_hotkey_deferral(qapp, monkeypatch):
    state = {K.CAMERA: True, K.ACCESSIBILITY: True, K.INPUT_MONITORING: False}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(
        "sigtouch.platformsupport.autostart.set_autostart", lambda *_: None)
    a = _make_app(monkeypatch)          # 启动时无 IM 权限(未 stub _setup_hotkey——测真实守卫)
    state[K.INPUT_MONITORING] = True     # 运行中授予
    a._on_permissions_changed()
    assert a._hotkey_needs_restart is True
    listeners_before = a._hotkey_listener
    a._apply_light_settings()            # 普通设置改动不得建监听器
    assert a._hotkey_listener is listeners_before is None
