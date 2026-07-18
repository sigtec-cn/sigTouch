import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_dialog_loads_defaults_and_applies_changes(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    cfg = Config(backend={})
    dlg = SettingsDialog(cfg)
    # 加载:控件反映默认值
    assert dlg.field_widget("camera/index").value() == 0
    assert dlg.field_widget("gestures/enter").isChecked() is True
    # 修改并应用
    dlg.field_widget("camera/index").setValue(2)
    dlg.field_widget("display/screen_diag_inch").setValue(55.0)
    dlg.field_widget("gestures/enter").setChecked(False)
    applied = []
    dlg.settings_applied.connect(lambda: applied.append(True))
    dlg.apply()
    assert cfg.get("camera/index") == 2
    assert cfg.get("display/screen_diag_inch") == pytest.approx(55.0)
    assert cfg.get("gestures/enter") is False
    assert applied == [True]


def test_active_hand_and_color_roundtrip(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    cfg = Config(backend={})
    dlg = SettingsDialog(cfg)
    # 默认加载
    hand_widget = dlg.field_widget("interaction/active_hand")
    assert hand_widget.currentData() == "Right"
    color_widget = dlg.field_widget("display/overlay_color")
    # 修改并应用(setter 经注册表,与 _load 同路)
    dlg._fields["interaction/active_hand"][2]("Left")
    dlg._fields["display/overlay_color"][2]("#112233")
    dlg.apply()
    assert cfg.get("interaction/active_hand") == "Left"
    assert cfg.get("display/overlay_color") == "#112233"
    assert color_widget.text() == "#112233"


def test_color_button_click_path_updates_field(qapp, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog

    from sigtouch.ui.settings_dialog import SettingsDialog
    cfg = Config(backend={})
    dlg = SettingsDialog(cfg)
    monkeypatch.setattr(QColorDialog, "getColor",
                        staticmethod(lambda *a, **k: QColor("#abcdef")))
    dlg.field_widget("display/overlay_color").click()
    dlg.apply()
    assert cfg.get("display/overlay_color").lower() == "#abcdef"
