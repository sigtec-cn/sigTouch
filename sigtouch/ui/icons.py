"""托盘图标:纯代码绘制,免资源文件。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

COLOR_ACTIVE = "#2ecc71"
COLOR_PAUSED = "#95a5a6"
COLOR_ERROR = "#e74c3c"
COLOR_PERMISSION = "#f1c40f"


def make_icon(color_hex: str) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color_hex))
    p.drawEllipse(2, 2, 60, 60)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(20, 30, 24, 22)                      # 掌
    for x, h in ((14, 14), (22, 18), (30, 20), (38, 18), (46, 13)):
        p.drawRoundedRect(x, 34 - h, 6, h, 3, 3)       # 五指圆头短柱
    p.end()
    return QIcon(pm)
