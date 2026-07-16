"""全屏透明点击穿透覆盖层:Oculus 风格半透明手部轮廓 + 手势反馈图标。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from sigtouch.config import Config
from sigtouch.perception.types import HandFrame

_FINGER_CHAINS = [
    [0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [5, 9, 10, 11, 12],
    [9, 13, 14, 15, 16], [13, 17, 18, 19, 20], [0, 17],
]
_PALM_LOOP = [0, 5, 9, 13, 17]


def scaled_points(landmarks, w: int, h: int, scale: float):
    """归一化关键点→像素坐标,围绕质心放大 scale 倍(远距离时手画得更大)。"""
    px = [(x * w, y * h) for x, y, _ in landmarks]
    cx = sum(p[0] for p in px) / len(px)
    cy = sum(p[1] for p in px) / len(px)
    return [((x - cx) * scale + cx, (y - cy) * scale + cy) for x, y in px]


class OverlayWindow(QWidget):
    def __init__(self, cfg: Config):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self._cfg = cfg
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._hand: HandFrame | None = None
        self._scale = 1.0
        self._feedback: str | None = None
        self._feedback_frames = 0

    def apply_screen(self) -> None:
        screens = QGuiApplication.screens()
        idx = min(self._cfg.get("display/monitor"), len(screens) - 1)
        self.setGeometry(screens[idx].geometry())
        self.show()

    def update_hand(self, hand: HandFrame, scale: float,
                    feedback: str | None) -> None:
        self._hand = hand
        self._scale = scale
        if feedback:                     # 反馈图标保持约 0.5s(15 帧)
            self._feedback = feedback
            self._feedback_frames = 15
        elif self._feedback_frames > 0:
            self._feedback_frames -= 1
            if self._feedback_frames == 0:
                self._feedback = None
        self.update()

    def clear(self) -> None:
        self._hand = None
        self._feedback = None
        self._feedback_frames = 0
        self.update()

    def paintEvent(self, event) -> None:
        if self._hand is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._cfg.get("display/overlay_color"))
        opacity = self._cfg.get("display/overlay_opacity")
        pts = scaled_points(self._hand.landmarks, self.width(), self.height(),
                            self._scale)
        base_w = max(6.0, self.height() / 90.0) * self._scale

        # 外圈微光 + 主描边(两遍绘制)
        for width, alpha in ((base_w * 2.2, opacity * 0.25), (base_w, opacity)):
            pen = QPen(color)
            pen.setWidthF(width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            color.setAlphaF(min(1.0, alpha))
            pen.setColor(color)
            p.setPen(pen)
            for chain in _FINGER_CHAINS:
                for a, b in zip(chain, chain[1:]):
                    p.drawLine(QPointF(*pts[a]), QPointF(*pts[b]))

        # 掌心半透明填充
        fill = QColor(color)
        fill.setAlphaF(opacity * 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPolygon(QPolygonF([QPointF(*pts[i]) for i in _PALM_LOOP]))

        if self._feedback:
            wrist = pts[0]
            p.setPen(QColor(color.red(), color.green(), color.blue(), 230))
            p.setFont(QFont("", int(28 * self._scale)))
            p.drawText(QPointF(wrist[0] + 40, wrist[1] - 40), self._feedback)
        p.end()
