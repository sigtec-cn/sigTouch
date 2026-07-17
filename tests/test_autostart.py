import sys

import pytest

from sigtouch.platformsupport import autostart


@pytest.mark.skipif(sys.platform == "win32", reason="win32 走注册表,人工验证")
def test_set_and_unset_autostart_roundtrip(tmp_path):
    assert autostart.is_autostart_enabled(home=tmp_path) is False
    autostart.set_autostart(True, home=tmp_path)
    assert autostart.is_autostart_enabled(home=tmp_path) is True
    # 落盘文件包含启动命令
    files = list(tmp_path.rglob("*sigtouch*")) + list(tmp_path.rglob("*SigTouch*"))
    assert files, "应生成 LaunchAgent plist 或 autostart .desktop"
    assert "sigtouch" in files[0].read_text().lower()
    autostart.set_autostart(False, home=tmp_path)
    assert autostart.is_autostart_enabled(home=tmp_path) is False


def test_accessibility_ok_returns_bool():
    from sigtouch.platformsupport import permissions
    assert isinstance(permissions.accessibility_ok(), bool)
