"""托盘图标:纯代码绘制,免资源文件。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

COLOR_ACTIVE = "#2ecc71"
COLOR_PAUSED = "#95a5a6"
COLOR_ERROR = "#e74c3c"


def make_icon(color_hex: str) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color_hex))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(8, 8, 48, 48)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(24, 18, 7, 22)   # 简化的"手指"示意
    p.drawEllipse(34, 16, 7, 24)
    p.end()
    return QIcon(pm)
