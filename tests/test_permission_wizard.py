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
