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
    if sys.platform == "darwin":
        import plistlib
        plist = plistlib.loads(files[0].read_bytes())
        assert plist["Label"] == "cn.sigtec.sigtouch"
        assert plist["RunAtLoad"] is True
        args = plist["ProgramArguments"]
        assert args[0] == sys.executable  # 空格路径不被拆碎
        assert args[1:] == ["-m", "sigtouch"]
    autostart.set_autostart(False, home=tmp_path)
    assert autostart.is_autostart_enabled(home=tmp_path) is False


@pytest.mark.skipif(sys.platform != "darwin", reason="darwin plist branch")
def test_spaced_executable_path_stays_one_argument(tmp_path, monkeypatch):
    import plistlib
    monkeypatch.setattr(sys, "executable", "/Applications/My App.app/Contents/MacOS/python3")
    autostart.set_autostart(True, home=tmp_path)
    plist_file = tmp_path / "Library" / "LaunchAgents" / "cn.sigtec.sigtouch.plist"
    plist = plistlib.loads(plist_file.read_bytes())
    assert plist["ProgramArguments"][0] == "/Applications/My App.app/Contents/MacOS/python3"
