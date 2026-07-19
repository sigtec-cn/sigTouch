import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dlg(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    return SettingsDialog(Config(backend={}))


def test_light_key_applies_immediately_and_signals(qapp):
    dlg = _dlg(qapp)
    got = []
    dlg.settings_applied.connect(lambda: got.append(1))
    dlg.field_widget("display/overlay_opacity").setValue(80)  # 滑杆 80%
    assert dlg._cfg.get("display/overlay_opacity") == pytest.approx(0.80)
    assert got == []                                    # 尚未发出,合并进 200ms 防抖
    assert dlg._apply_timer.isActive() is True          # 轻量键走 apply 防抖
    assert dlg._restart_timer.isActive() is False       # 轻量键不碰重启防抖

    dlg.field_widget("display/overlay_opacity").setValue(85)  # 防抖期内再次改动
    assert dlg._cfg.get("display/overlay_opacity") == pytest.approx(0.85)  # 配置仍即时写入
    assert got == []                                    # 仍未发出

    dlg._apply_timer.stop()
    dlg._apply_timer.timeout.emit()                      # 模拟防抖到期
    assert got == [1]                                    # 两次改动合并为一次信号


def test_restart_key_debounces_single_signal(qapp):
    dlg = _dlg(qapp)
    fired = []
    dlg.vision_restart_needed.connect(lambda: fired.append(1))
    dlg.field_widget("camera/index").setValue(1)
    dlg.field_widget("camera/index").setValue(2)        # 连续两次改动
    assert dlg._cfg.get("camera/index") == 2            # 配置即时写入
    assert fired == [] and dlg._restart_timer.isActive()
    dlg._restart_timer.stop()
    dlg._restart_timer.timeout.emit()                   # 模拟防抖到期
    assert fired == [1]                                 # 合并为一次


def test_load_does_not_emit_signals(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    cfg = Config(backend={"camera/index": 2})
    got = []
    dlg = SettingsDialog(cfg)                           # 构造期 _load 不触发
    dlg.settings_applied.connect(lambda: got.append("a"))
    dlg.vision_restart_needed.connect(lambda: got.append("v"))
    dlg._load()                                         # 显式重载同样安静
    assert got == []
    assert dlg._apply_timer.isActive() is False


def test_restore_defaults_reverts_and_applies(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("camera/index").setValue(3)
    dlg.field_widget("display/overlay_opacity").setValue(90)
    assert dlg._cfg.get("camera/index") == 3
    dlg._restore_defaults()
    assert dlg._cfg.get("camera/index") == 0
    assert dlg._cfg.get("display/overlay_opacity") == pytest.approx(0.35)
    assert dlg._restart_timer.isActive() is True        # 默认值可能改了摄像头组 → 走防抖


def test_slider_mappings(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("interaction/box_margin").setValue(20)
    assert dlg._cfg.get("interaction/box_margin") == pytest.approx(0.20)
    dlg.field_widget("interaction/smooth_min_cutoff").setValue(25)
    assert dlg._cfg.get("interaction/smooth_min_cutoff") == pytest.approx(2.5)


def test_restart_debounce_survives_dialog_close(qapp):
    dlg = _dlg(qapp)
    fired = []
    dlg.vision_restart_needed.connect(lambda: fired.append(1))
    dlg.field_widget("camera/index").setValue(1)
    dlg.close()
    dlg._restart_timer.stop()
    dlg._restart_timer.timeout.emit()                   # 关闭后手动模拟防抖到期
    assert fired == [1]                                 # 关闭对话框不丢失待发信号


def test_pause_hotkey_editing_finished_applies(qapp):
    dlg = _dlg(qapp)
    field = dlg.field_widget("general/pause_hotkey")
    field.setText("<ctrl>+p")
    field.editingFinished.emit()
    assert dlg._cfg.get("general/pause_hotkey") == "<ctrl>+p"
    assert dlg._apply_timer.isActive() is True           # 轻量键走 apply 防抖
    assert dlg._restart_timer.isActive() is False        # 不是重启键


def test_scale_keys_are_light_and_instant(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("display/camera_screen_offset_m").setValue(1.5)
    assert dlg._cfg.get("display/camera_screen_offset_m") == pytest.approx(1.5)
    dlg.field_widget("display/hand_scale_multiplier").setValue(200)
    assert dlg._cfg.get("display/hand_scale_multiplier") == pytest.approx(2.0)
    assert dlg._apply_timer.isActive() is True     # 轻量合并
    assert dlg._restart_timer.isActive() is False  # 不触发视觉重启
