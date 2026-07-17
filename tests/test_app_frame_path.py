"""集成测试:SigTouchApp._on_result 的完整帧路径(未被其余单元测试覆盖的接缝)。

覆盖两个真实回归场景:
1. 拖拽中人脸消失超过宽限期 → 挂起分支必须补发 DRAG_END,不留鼠标左键卡死。
2. 拖拽中用户点"应用"设置 → 旧状态机被丢弃前必须先 release_all()。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

import sigtouch.app as appmod
from sigtouch.config import Config
from sigtouch.interaction.gestures import EventKind
from sigtouch.perception.types import FrameResult
from tests.hand_fixtures import open_hand, pinch_index


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class FakeInjector:
    """记录 move/dispatch/release_all 调用顺序,不接触真实 pynput。"""

    def __init__(self, mouse=None, keyboard=None):
        self.calls = []

    def move(self, x, y) -> None:
        self.calls.append(("move", x, y))

    def dispatch(self, ev) -> None:
        self.calls.append(("dispatch", ev.kind))

    def release_all(self) -> None:
        self.calls.append(("release_all",))


def _stub_vision(self) -> None:
    self._vision = SimpleNamespace(
        set_idle=lambda b: None,
        set_preview=lambda b: None,
        stop=lambda: None,
        isRunning=lambda: True,
        last_frame_monotonic_ms=0,
    )


@pytest.fixture
def app_obj(qapp, monkeypatch):
    monkeypatch.setattr(appmod, "Injector", FakeInjector)
    monkeypatch.setattr(appmod.SigTouchApp, "_start_vision", _stub_vision)
    monkeypatch.setattr(appmod.SigTouchApp, "_setup_hotkey", lambda self: None)
    cfg = Config(backend={})
    a = appmod.SigTouchApp(cfg)
    yield a


def _drive_to_dragging(app_obj) -> None:
    """三帧序列把手势状态机推入 DRAGGING:张手 → 捏合(t=33)→ 保持捏合超过 250ms(t=400)。"""
    app_obj._on_result(FrameResult(timestamp_ms=0, hand=open_hand(),
                                   face_distance_m=0.6, face_present=True))
    app_obj._on_result(FrameResult(timestamp_ms=33, hand=pinch_index(),
                                   face_distance_m=0.6, face_present=True))
    app_obj._on_result(FrameResult(timestamp_ms=400, hand=pinch_index(),
                                   face_distance_m=0.6, face_present=True))


def test_suspend_mid_drag_dispatches_drag_end_and_releases(app_obj):
    _drive_to_dragging(app_obj)
    dispatched_kinds = [c[1] for c in app_obj._injector.calls if c[0] == "dispatch"]
    assert EventKind.DRAG_START in dispatched_kinds, \
        "拖拽应在保持捏合超过 click_max_ms 后触发 DRAG_START"

    # 5000 - 400 = 4600ms > 3000ms 宽限期 → 挂起分支
    app_obj._on_result(FrameResult(timestamp_ms=5000, hand=None,
                                   face_distance_m=0.6, face_present=False))

    calls = app_obj._injector.calls
    drag_start_idx = next(i for i, c in enumerate(calls)
                          if c[0] == "dispatch" and c[1] is EventKind.DRAG_START)
    drag_end_idx = next(i for i, c in enumerate(calls)
                        if c[0] == "dispatch" and c[1] is EventKind.DRAG_END)
    release_idx = next(i for i, c in enumerate(calls) if c[0] == "release_all")

    assert drag_start_idx < drag_end_idx, "DRAG_START 必须先于 DRAG_END"
    assert drag_start_idx < release_idx, "DRAG_START 必须先于挂起时的 release_all"
    assert app_obj._overlay._hand is None, "挂起后 overlay 应被清空"


def test_settings_applied_mid_drag_releases_button(app_obj, monkeypatch):
    _drive_to_dragging(app_obj)
    dispatched_kinds = [c[1] for c in app_obj._injector.calls if c[0] == "dispatch"]
    assert EventKind.DRAG_START in dispatched_kinds

    # _restart_vision 会断开信号,stub 视觉线程没有 Qt 信号对象,规避掉
    monkeypatch.setattr(app_obj, "_restart_vision", lambda: None)
    monkeypatch.setattr("sigtouch.platformsupport.autostart.set_autostart",
                        lambda enabled: None)

    calls_before = len(app_obj._injector.calls)
    app_obj._on_settings_applied()

    release_calls = [c for c in app_obj._injector.calls[calls_before:]
                     if c[0] == "release_all"]
    assert release_calls, "settings applied 中途拖拽必须 release_all() 防止鼠标卡死"
