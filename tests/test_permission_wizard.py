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
    assert w._status_labels[K.CAMERA].text().startswith("✓")
    assert w._status_labels[K.ACCESSIBILITY].text().startswith("✗")
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
    assert w._status_labels[K.ACCESSIBILITY].text().startswith("✓")


def test_poll_timer_stops_when_granted_or_hidden(qapp):
    state = {K.CAMERA: True, K.ACCESSIBILITY: False, K.INPUT_MONITORING: True}
    w = _wizard(state, [])
    assert w._timer.isActive() is True          # 构造时未全就绪 → 轮询中
    state[K.ACCESSIBILITY] = True
    w.refresh()
    assert w._timer.isActive() is False         # 全就绪 → 停
    state[K.ACCESSIBILITY] = False
    w._was_all_granted = False
    w.show(); w.hide()
    assert w._timer.isActive() is False         # 隐藏 → 停


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


def test_wizard_stays_open_when_restart_needed(qapp, monkeypatch):
    from PySide6.QtCore import QTimer
    from sigtouch.ui.permission_wizard import PermissionWizard
    state = {K.CAMERA: True, K.ACCESSIBILITY: True, K.INPUT_MONITORING: True}
    shots = []
    monkeypatch.setattr(QTimer, "singleShot",
                        staticmethod(lambda ms, fn: shots.append(ms)))
    w = PermissionWizard(checker=lambda: dict(state),
                         requester=lambda k: None, opener=lambda k: None,
                         restart_hint=lambda: True)
    assert w._restart_row.isVisibleTo(w) is True
    assert shots == []                      # 不自动关闭
    # 无需重启的普通全就绪:仍自动关闭
    w2 = PermissionWizard(checker=lambda: dict(state),
                          requester=lambda k: None, opener=lambda k: None)
    assert shots and shots[-1] == 2000      # 构造时 refresh 触发关闭调度


def test_tray_permission_state_and_menu(qapp):
    from sigtouch.ui.tray import TrayController
    t = TrayController()
    t.set_state("permission")            # 不抛即可(图标/文案人工核对)
    texts = [a.text() for a in t._menu.actions()]
    assert any("权限设置" in x for x in texts)
    # 带快捷键:tooltip 与切换项文案含快捷键
    t.set_state("active", "Ctrl+Alt+P")
    assert "Ctrl+Alt+P" in t._tray.toolTip()
    assert "Ctrl+Alt+P" in t._toggle_action.text()
    # 不带快捷键:退回原文案(无括号后缀)
    t.set_state("active")
    assert "Ctrl+Alt+P" not in t._toggle_action.text()
    assert t._toggle_action.text() == "⏸ 暂停"
    t.set_state("paused", "Ctrl+Alt+P")
    assert t._toggle_action.text() == "▶ 恢复 (Ctrl+Alt+P)"
    assert "恢复" in t._tray.toolTip()
