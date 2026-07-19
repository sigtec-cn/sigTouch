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
