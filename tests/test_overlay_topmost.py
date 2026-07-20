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


def test_apply_screen_respects_topmost_flag(qapp, monkeypatch):
    import sigtouch.ui.overlay as ov
    pins = []
    monkeypatch.setattr(ov, "pin_window_topmost", lambda w: pins.append(1))
    monkeypatch.setattr(ov, "unpin_window_topmost", lambda w: None)
    w = ov.OverlayWindow(Config(backend={}))
    w.apply_screen()
    assert not w.isVisible() and pins == []   # 非置顶态:仅设几何,不显示不 pin
    w.set_topmost(True)
    pins.clear()
    w.apply_screen()
    assert w.isVisible() and pins == [1]      # 置顶态:重申 show+pin(换显示器场景)
