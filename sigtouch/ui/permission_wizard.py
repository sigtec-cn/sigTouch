"""权限引导窗:卡片式逐项状态 + 主动请求 + 打开系统设置,自动轮询刷新。
布局为 v1.3 卡片化;行为契约(注入依赖/升沿信号/timer 生命周期)与 v1.1 一致。"""
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout)

from sigtouch.platformsupport import permissions as perms
from sigtouch.platformsupport.permissions import PermissionKind
from sigtouch.ui.theme import repolish

_ROWS = [
    (PermissionKind.CAMERA, "📷", "摄像头", "识别手部与人脸(核心功能)"),
    (PermissionKind.ACCESSIBILITY, "🖱️", "辅助功能", "控制鼠标与键盘(手势注入)"),
    (PermissionKind.INPUT_MONITORING, "⌨️", "输入监控", "全局暂停快捷键"),
]
_POLL_MS = 2000
_CLOSE_DELAY_MS = 2000


class PermissionWizard(QDialog):
    all_granted = Signal()

    def __init__(self, checker=None, requester=None, opener=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 权限设置")
        self.setFixedWidth(520)
        self._checker = checker
        self._requester = requester
        self._opener = opener
        self._was_all_granted = False
        self._status_labels: dict[PermissionKind, QLabel] = {}
        self._request_buttons: dict[PermissionKind, QPushButton] = {}
        self._open_buttons: dict[PermissionKind, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        title = QLabel("SigTouch 权限设置")
        title.setProperty("class", "title")
        layout.addWidget(title)
        sub = QLabel("SigTouch 需要以下系统权限。授权后无需重启,应用会自动激活。")
        sub.setProperty("class", "muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self._banner = QFrame()
        self._banner.setProperty("class", "banner-ok")
        btext = QLabel("✓ 全部权限已就绪,SigTouch 已自动激活")
        btext.setStyleSheet("color: white; font-weight: 600; background: transparent;")
        bl = QHBoxLayout(self._banner)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.addWidget(btext)
        self._banner.setVisible(False)
        layout.addWidget(self._banner)

        for kind, icon, name, why in _ROWS:
            card = QFrame()
            card.setProperty("class", "card")
            grid = QGridLayout(card)
            grid.setContentsMargins(14, 10, 14, 10)
            ic = QLabel(icon)
            ic.setStyleSheet("font-size: 22px; background: transparent;")
            grid.addWidget(ic, 0, 0, 2, 1)
            head = QLabel(f"<b>{name}</b>")
            grid.addWidget(head, 0, 1)
            badge = QLabel()
            self._status_labels[kind] = badge
            grid.addWidget(badge, 0, 2)
            hint = QLabel(why)
            hint.setProperty("class", "muted")
            grid.addWidget(hint, 1, 1, 1, 2)
            req = QPushButton("请求权限")
            req.setProperty("class", "primary")
            req.clicked.connect(lambda _=False, k=kind: self._request(k))
            self._request_buttons[kind] = req
            grid.addWidget(req, 0, 3, 2, 1)
            opn = QPushButton("打开系统设置")
            opn.clicked.connect(lambda _=False, k=kind: self._open(k))
            self._open_buttons[kind] = opn
            grid.addWidget(opn, 0, 4, 2, 1)
            layout.addWidget(card)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(_POLL_MS)
        self.refresh()

    def _snapshot(self) -> dict:
        return self._checker() if self._checker else perms.snapshot()

    def _request(self, kind: PermissionKind) -> None:
        (self._requester or perms.request)(kind)

    def _open(self, kind: PermissionKind) -> None:
        (self._opener or perms.open_settings)(kind)

    def refresh(self) -> None:
        snap = self._snapshot()
        for kind, badge in self._status_labels.items():
            ok = bool(snap.get(kind, True))
            badge.setText("✓ 已授权" if ok else "✗ 未授权")
            badge.setProperty("class", "badge-ok" if ok else "badge-danger")
            repolish(badge)
            self._request_buttons[kind].setEnabled(not ok)
        granted = all(snap.values())
        self._banner.setVisible(granted)
        if granted:
            self._timer.stop()
        if granted and not self._was_all_granted:
            self.all_granted.emit()
            QTimer.singleShot(_CLOSE_DELAY_MS, self.close)
        self._was_all_granted = granted

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        if not self._was_all_granted:
            self._timer.start(_POLL_MS)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()
