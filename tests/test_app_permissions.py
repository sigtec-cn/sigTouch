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
