"""系统托盘:三态图标 + 菜单。"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from sigtouch.ui import lucide, theme
from sigtouch.ui.icons import COLOR_ACTIVE, COLOR_ERROR, COLOR_PAUSED, COLOR_PERMISSION, make_icon

_STATE_META = {
    "active": (COLOR_ACTIVE, "SigTouch:运行中", "暂停"),
    "paused": (COLOR_PAUSED, "SigTouch:已暂停", "恢复"),
    "error": (COLOR_ERROR, "SigTouch:摄像头异常", "暂停"),
    "permission": (COLOR_PERMISSION, "SigTouch:等待权限授权", "暂停"),
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
        self._toggle_action = QAction("暂停")
        self._toggle_action.setIcon(lucide.icon("pause", theme.TEXT, 14))
        self._toggle_action.triggered.connect(self.toggle_requested)
        menu.addAction(self._toggle_action)
        settings = QAction("设置…", menu)
        settings.setIcon(lucide.icon("settings", theme.TEXT, 14))
        settings.triggered.connect(self.settings_requested)
        menu.addAction(settings)
        perms_action = QAction("权限设置…", menu)
        perms_action.setIcon(lucide.icon("shield", theme.TEXT, 14))
        perms_action.triggered.connect(self.permissions_requested)
        menu.addAction(perms_action)
        preview = QAction("调试预览", menu)
        preview.setIcon(lucide.icon("video", theme.TEXT, 14))
        preview.triggered.connect(self.preview_requested)
        menu.addAction(preview)
        menu.addSeparator()
        quit_ = QAction("退出", menu)
        quit_.setIcon(lucide.icon("power", theme.TEXT, 14))
        quit_.triggered.connect(self.quit_requested)
        menu.addAction(quit_)
        self._menu = menu  # 持引用防 GC
        self._tray.setContextMenu(menu)
        self._tray.setToolTip("SigTouch:运行中")
        self._tray.show()

    def set_state(self, state: str, hotkey_label: str = "") -> None:
        color, tip, action_word = _STATE_META[state]
        self._tray.setIcon(make_icon(color))
        self._toggle_action.setIcon(
            lucide.icon("play" if action_word == "恢复" else "pause", theme.TEXT, 14))
        if hotkey_label:
            self._tray.setToolTip(f"{tip} ({hotkey_label} {action_word})")
            self._toggle_action.setText(f"{action_word} ({hotkey_label})")
        else:
            self._tray.setToolTip(tip)
            self._toggle_action.setText(action_word)
