import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dlg(qapp, **backend):
    from sigtouch.ui.settings_dialog import SettingsDialog
    return SettingsDialog(Config(backend=backend))


def test_status_badge_reflects_state(qapp):
    dlg = _dlg(qapp)
    dlg.set_running_state("active")
    assert "使用中" in dlg._status_badge.text()
    dlg.set_running_state("paused")
    assert "已暂停" in dlg._status_badge.text()
    dlg.set_running_state("permission")
    assert "权限" in dlg._status_badge.text()
    dlg.set_running_state("error")
    assert "摄像头" in dlg._status_badge.text()


def test_hotkey_line_shows_formatted_key(qapp):
    dlg = _dlg(qapp, **{"general/pause_hotkey": "<ctrl>+<alt>+p"})
    dlg.refresh_hotkey_label()
    assert "Ctrl+Alt+P" in dlg._hotkey_line.text()


def test_hotkey_line_updates_on_field_change(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("general/pause_hotkey").setText("<cmd>+<shift>+s")
    dlg.field_widget("general/pause_hotkey").editingFinished.emit()
    assert "Cmd+Shift+S" in dlg._hotkey_line.text()
