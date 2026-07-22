# tests/test_new_behaviors.py — 暂停关摄像头 / 设置快捷键 / 屏幕检测守卫
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import sigtouch.app as app_module
from sigtouch.app import SigTouchApp
from sigtouch.config import Config
from sigtouch.platformsupport.permissions import PermissionKind as K


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


class _VisionStub:
    def __init__(self):
        self.last_frame_monotonic_ms = 0
        self.stopped = False
        self.idle = None
        self.preview = None

    def set_idle(self, b):
        self.idle = b

    def set_preview(self, b):
        self.preview = b

    def stop(self):
        self.stopped = True

    def isRunning(self):
        return True

    # 信号替身:可 disconnect
    class _Sig:
        def connect(self, f):
            pass

        def disconnect(self):
            pass

        def emit(self, *a):
            pass

    result_ready = _Sig()
    preview_frame = _Sig()
    camera_error = _Sig()
    recovered = _Sig()


def _patch_perms(monkeypatch, state):
    monkeypatch.setattr(app_module.perms, "check", lambda k: state[k])
    monkeypatch.setattr(app_module.perms, "snapshot", lambda: dict(state))
    monkeypatch.setattr(app_module.perms, "all_granted",
                        lambda: all(state.values()))
    monkeypatch.setattr(app_module.perms, "request", lambda k: None)


def _make_app(monkeypatch, cfg=None):
    monkeypatch.setattr(app_module.SigTouchApp, "_start_vision",
                        lambda self: setattr(self, "_vision", _VisionStub()))
    return SigTouchApp(cfg or Config(backend={}))


# ---- ⑥ 暂停关摄像头 ----
def test_pause_stops_vision_and_resume_restarts(qapp, monkeypatch):
    _patch_perms(monkeypatch, {k: True for k in K})
    a = _make_app(monkeypatch)
    first = a._vision

    restarts = []
    monkeypatch.setattr(a, "_start_vision", lambda: restarts.append(1))

    a._toggle_pause()            # 暂停
    assert a._paused is True
    assert a._vision is None     # 摄像头关闭
    assert first.stopped is True

    a._toggle_pause()            # 恢复
    assert a._paused is False
    assert restarts, "恢复应重启视觉(重开摄像头)"


def test_watchdog_does_not_restart_while_paused(qapp, monkeypatch):
    _patch_perms(monkeypatch, {k: True for k in K})
    a = _make_app(monkeypatch)
    monkeypatch.setattr(a, "_restart_vision",
                        lambda: (_ for _ in ()).throw(AssertionError("不应重启")))
    a._toggle_pause()
    a._check_watchdog()          # vision=None 且 paused:应直接返回,不重启


def test_on_result_dropped_when_vision_none(qapp, monkeypatch):
    _patch_perms(monkeypatch, {k: True for k in K})
    a = _make_app(monkeypatch)
    a._vision = None
    from sigtouch.perception.types import FrameResult
    a._on_result(FrameResult(timestamp_ms=0, hand=None, face_distance_m=None))


# ---- ④ 设置快捷键 ----
def test_settings_hotkey_registered(qapp, monkeypatch):
    _patch_perms(monkeypatch, {k: True for k in K})
    a = _make_app(monkeypatch)
    a._hotkey_needs_restart = False
    a._im_granted_at_start = True

    captured = {}

    class FakeHotKeys:
        def __init__(self, mapping):
            captured["mapping"] = mapping

        def start(self):
            pass

        def stop(self):
            pass

    import pynput.keyboard as pk
    monkeypatch.setattr(pk, "GlobalHotKeys", FakeHotKeys)
    a._setup_hotkey()
    m = captured["mapping"]
    assert m[a._cfg.get("general/pause_hotkey").strip()]
    assert m[a._cfg.get("general/settings_hotkey").strip()]


def test_settings_hotkey_same_as_pause_not_duplicated(qapp, monkeypatch):
    _patch_perms(monkeypatch, {k: True for k in K})
    cfg = Config(backend={
        "general/pause_hotkey": "<ctrl>+<alt>+x",
        "general/settings_hotkey": "<ctrl>+<alt>+x"})
    a = _make_app(monkeypatch, cfg)
    a._hotkey_needs_restart = False

    captured = {}

    class FakeHotKeys:
        def __init__(self, mapping):
            captured["mapping"] = mapping

        def start(self):
            pass

        def stop(self):
            pass

    import pynput.keyboard as pk
    monkeypatch.setattr(pk, "GlobalHotKeys", FakeHotKeys)
    a._setup_hotkey()
    assert len(captured["mapping"]) == 1  # 同组合只注册一次


# ---- ⑤ 屏幕检测守卫 ----
def test_screen_detect_skipped_offscreen(qapp, monkeypatch):
    _patch_perms(monkeypatch, {k: True for k in K})
    cfg = Config(backend={})
    a = _make_app(monkeypatch, cfg)
    # offscreen:_detect_screen_size 不应改动默认值、不应置 detected
    assert cfg.get("display/screen_diag_inch") == 24.0
    assert cfg.get("display/screen_diag_detected") is False
