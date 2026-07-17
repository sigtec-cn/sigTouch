"""权限引导窗:逐项状态 + 主动请求 + 打开系统设置,2s 自动轮询刷新。"""
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QGridLayout, QLabel, QPushButton,
                               QVBoxLayout)

from sigtouch.platformsupport import permissions as perms
from sigtouch.platformsupport.permissions import PermissionKind

_ROWS = [
    (PermissionKind.CAMERA, "摄像头", "识别手部与人脸(核心功能)"),
    (PermissionKind.ACCESSIBILITY, "辅助功能", "控制鼠标与键盘(手势注入)"),
    (PermissionKind.INPUT_MONITORING, "输入监控", "全局暂停快捷键"),
]
_POLL_MS = 2000
_CLOSE_DELAY_MS = 2000


class PermissionWizard(QDialog):
    all_granted = Signal()

    def __init__(self, checker=None, requester=None, opener=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 权限设置")
        # 依赖调用时解析,保证测试可注入、monkeypatch perms.* 也生效
        self._checker = checker
        self._requester = requester
        self._opener = opener
        self._was_all_granted = False
        self._status_labels: dict[PermissionKind, QLabel] = {}
        self._request_buttons: dict[PermissionKind, QPushButton] = {}
        self._open_buttons: dict[PermissionKind, QPushButton] = {}

        layout = QVBoxLayout(self)
        intro = QLabel("SigTouch 需要以下系统权限。授权后无需重启,应用会自动激活。")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        grid = QGridLayout()
        for row, (kind, name, why) in enumerate(_ROWS):
            status = QLabel()
            self._status_labels[kind] = status
            grid.addWidget(status, row, 0)
            grid.addWidget(QLabel(f"<b>{name}</b> — {why}"), row, 1)
            req = QPushButton("请求权限")
            req.clicked.connect(lambda _=False, k=kind: self._request(k))
            self._request_buttons[kind] = req
            grid.addWidget(req, row, 2)
            opn = QPushButton("打开系统设置")
            opn.clicked.connect(lambda _=False, k=kind: self._open(k))
            self._open_buttons[kind] = opn
            grid.addWidget(opn, row, 3)
        layout.addLayout(grid)

        self._banner = QLabel("")
        layout.addWidget(self._banner)

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
        for kind, label in self._status_labels.items():
            ok = bool(snap.get(kind, True))
            label.setText("✓" if ok else "✗")
            label.setStyleSheet(
                f"color: {'#2ecc71' if ok else '#e74c3c'}; font-size: 18px;")
            self._request_buttons[kind].setEnabled(not ok)
        granted = all(snap.values())
        if granted and not self._was_all_granted:
            self._banner.setText("✓ 全部权限已就绪,SigTouch 已自动激活")
            self.all_granted.emit()
            QTimer.singleShot(_CLOSE_DELAY_MS, self.close)
        elif not granted:
            self._banner.setText("")
        self._was_all_granted = granted
        if granted:
            self._timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        if not self._was_all_granted:
            self._timer.start(_POLL_MS)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()
