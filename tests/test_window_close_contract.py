# tests/test_window_close_contract.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config
from sigtouch.platformsupport.permissions import PermissionKind as K


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def test_settings_close_hides_but_app_survives(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(Config(backend={}))
    dlg.show()
    assert dlg.isVisible()
    dlg.close()
    assert not dlg.isVisible()               # 关窗=收起
    assert QApplication.instance() is not None


def test_wizard_close_hides_but_app_survives(qapp):
    from sigtouch.ui.permission_wizard import PermissionWizard
    w = PermissionWizard(checker=lambda: {k: True for k in K},
                         requester=lambda k: None, opener=lambda k: None)
    w.show()
    w.close()
    assert not w.isVisible()
    assert QApplication.instance() is not None
