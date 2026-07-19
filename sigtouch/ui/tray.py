"""系统托盘:三态图标 + 菜单。"""
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from sigtouch.ui.icons import COLOR_ACTIVE, COLOR_ERROR, COLOR_PAUSED, COLOR_PERMISSION, make_icon

_STATE_META = {
    "active": (COLOR_ACTIVE, "SigTouch:运行中", "⏸ 暂停"),
    "paused": (COLOR_PAUSED, "SigTouch:已暂停", "▶ 恢复"),
    "error": (COLOR_ERROR, "SigTouch:摄像头异常", "⏸ 暂停"),
    "permission": (COLOR_PERMISSION, "SigTouch:等待权限授权", "⏸ 暂停"),
}


class TrayController(QObject):
    toggle_requested = Signal()
    settings_requested = Signal()
    permissions_requested = Signal()
    preview_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(make_icon(COLOR_ACTIVE))
        menu = QMenu()
        self._toggle_action = QAction("⏸ 暂停")
        self._toggle_action.triggered.connect(self.toggle_requested)
        menu.addAction(self._toggle_action)
        settings = QAction("⚙️ 设置…", menu)
        settings.triggered.connect(self.settings_requested)
        menu.addAction(settings)
        perms_action = QAction("🔐 权限设置…", menu)
        perms_action.triggered.connect(self.permissions_requested)
        menu.addAction(perms_action)
        preview = QAction("🎥 调试预览", menu)
        preview.triggered.connect(self.preview_requested)
        menu.addAction(preview)
        menu.addSeparator()
        quit_text = "退出" if sys.platform == "win32" else "⏻ 退出"
        quit_ = QAction(quit_text, menu)
        quit_.triggered.connect(self.quit_requested)
        menu.addAction(quit_)
        self._menu = menu  # 持引用防 GC
        self._tray.setContextMenu(menu)
        self._tray.setToolTip("SigTouch:运行中")
        self._tray.show()

    def set_state(self, state: str, hotkey_label: str = "") -> None:
        color, tip, toggle_text = _STATE_META[state]
        self._tray.setIcon(make_icon(color))
        if hotkey_label:
            # 切换动作词 = 去掉 emoji 前缀的核心("⏸ 暂停" -> "暂停")
            action_word = toggle_text.split(" ", 1)[-1]
            self._tray.setToolTip(f"{tip} ({hotkey_label} {action_word})")
            self._toggle_action.setText(f"{toggle_text} ({hotkey_label})")
        else:
            self._tray.setToolTip(tip)
            self._toggle_action.setText(toggle_text)
