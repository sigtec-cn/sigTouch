"""开机自启:Windows 注册表 Run / macOS LaunchAgent / Linux autostart .desktop。"""
import sys
from pathlib import Path

APP_NAME = "SigTouch"
_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):   # PyInstaller 打包后
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m sigtouch'


def _plist_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / "cn.sigtec.sigtouch.plist"


def _desktop_path(home: Path) -> Path:
    return home / ".config" / "autostart" / "sigtouch.desktop"


def set_autostart(enabled: bool, home: Path | None = None) -> None:
    if sys.platform == "win32":
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0,
                             winreg.KEY_SET_VALUE)
        with key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                                  _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return
    home = home or Path.home()
    if sys.platform == "darwin":
        path = _plist_path(home)
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            args = _launch_command().replace('"', "").split()
            items = "\n".join(f"    <string>{a}</string>" for a in args)
            path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>cn.sigtec.sigtouch</string>
  <key>ProgramArguments</key><array>
{items}
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
""")
        else:
            path.unlink(missing_ok=True)
        return
    # Linux
    path = _desktop_path(home)
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Exec={_launch_command()}
X-GNOME-Autostart-enabled=true
""")
    else:
        path.unlink(missing_ok=True)


def is_autostart_enabled(home: Path | None = None) -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0,
                                 winreg.KEY_READ)
            with key:
                winreg.QueryValueEx(key, APP_NAME)
            return True
        except FileNotFoundError:
            return False
    home = home or Path.home()
    path = _plist_path(home) if sys.platform == "darwin" else _desktop_path(home)
    return path.exists()
