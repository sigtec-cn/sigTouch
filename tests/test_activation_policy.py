# tests/test_activation_policy.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import sigtouch.app as app_module
from sigtouch.app import SigTouchApp
from sigtouch.config import Config


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


class _VisionStub:
    last_frame_monotonic_ms = 0

    def set_idle(self, b):
        pass

    def set_preview(self, b):
        pass

    def stop(self):
        pass

    def isRunning(self):
        return True


def _make_app(monkeypatch):
    monkeypatch.setattr(
        SigTouchApp, "_start_vision",
        lambda self: setattr(self, "_vision", _VisionStub()))
    return SigTouchApp(Config(backend={}))


def _record_native(monkeypatch):
    calls = []
    monkeypatch.setattr(app_module.native, "set_activation_policy_regular",
                        lambda: calls.append("regular"))
    monkeypatch.setattr(app_module.native, "set_activation_policy_accessory",
                        lambda: calls.append("accessory"))
    monkeypatch.setattr(app_module.native, "activate_app",
                        lambda: calls.append("activate"))
    return calls


def test_present_window_activates_before_show(qapp, monkeypatch):
    calls = _record_native(monkeypatch)
    a = _make_app(monkeypatch)
    a._present_window(a._settings_dlg)
    # 先切 Regular、再激活,窗口最后 show
    assert calls[:2] == ["regular", "activate"]
    assert a._settings_dlg.isVisible()


def test_restore_accessory_only_after_all_config_windows_hidden(qapp, monkeypatch):
    calls = _record_native(monkeypatch)
    a = _make_app(monkeypatch)
    a._present_window(a._settings_dlg)
    a._present_window(a._wizard)
    calls.clear()

    a._settings_dlg.hide()
    a._maybe_restore_accessory()
    assert "accessory" not in calls          # 向导还开着,不恢复

    a._wizard.hide()
    a._maybe_restore_accessory()
    assert "accessory" in calls              # 都关了才恢复纯托盘
