"""全屏透明点击穿透覆盖层:Oculus 风格半透明手部轮廓 + 手势反馈图标。"""
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QPainter,
                           QPainterPath, QPainterPathStroker, QPolygonF)
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from sigtouch.config import Config
from sigtouch.interaction.features import INDEX_TIP
from sigtouch.perception.types import HandFrame
from sigtouch.ui.native import pin_window_topmost, unpin_window_topmost

_FINGER_CHAINS = [
    [0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [5, 9, 10, 11, 12],
    [9, 13, 14, 15, 16], [13, 17, 18, 19, 20], [0, 17],
]
_PALM_LOOP = [0, 5, 9, 13, 17]


def target_screen_index(cfg: Config, screens) -> int:
    """把配置的目标显示器索引夹到 [0, len(screens)-1],避免显示器被拔掉后越界。"""
    idx = cfg.get("display/monitor")
    return max(0, min(idx, len(screens) - 1))


def scaled_points(landmarks, w: int, h: int, scale: float):
    """归一化关键点→像素坐标,围绕质心放大 scale 倍(远距离时手画得更大)。"""
    px = [(x * w, y * h) for x, y, _ in landmarks]
    cx = sum(p[0] for p in px) / len(px)
    cy = sum(p[1] for p in px) / len(px)
    return [((x - cx) * scale + cx, (y - cy) * scale + cy) for x, y in px]


def align_to_cursor(points, index_tip_idx, cursor_px):
    """整体平移点集,使 points[index_tip_idx] 与 cursor_px 重合(光标钉在食指尖)。"""
    dx = cursor_px[0] - points[index_tip_idx][0]
    dy = cursor_px[1] - points[index_tip_idx][1]
    return [(x + dx, y + dy) for x, y in points]


def fit_hand_to_screen(points, anchor_idx, screen_w, screen_h,
                       max_h_fraction, min_shrink=0.5):
    """围绕 anchor(食指尖)收缩手影:限制高度占屏比例,并尽量收进屏幕。

    anchor 点位置恒不变——光标始终钉在食指上(v1.2 契约)。

    min_shrink 仅约束尺寸收缩项;边缘收容始终优先(不裁切 > 不塌缩,食指尖恒在光标上)。
    """
    if len(points) < 2:
        return points
    ax, ay = points[anchor_idx]
    ys = [p[1] for p in points]
    bbox_h = max(ys) - min(ys)
    if bbox_h <= 0:
        return points

    # (a) 尺寸上限 —— 下限只约束这一项
    limit = screen_h * max_h_fraction
    k = limit / bbox_h if bbox_h > limit else 1.0
    k = max(min_shrink, k)

    # (b) 边缘收容:始终优先,可将 k 压到下限之下
    for x, y in points:
        dx, dy = x - ax, y - ay
        if dx > 0:
            k = min(k, (screen_w - ax) / dx)
        elif dx < 0:
            k = min(k, -ax / dx)
        if dy > 0:
            k = min(k, (screen_h - ay) / dy)
        elif dy < 0:
            k = min(k, -ay / dy)

    k = min(1.0, k)
    if k >= 1.0:
        return points
    return [(ax + (x - ax) * k, ay + (y - ay) * k) for x, y in points]


def silhouette_path(points, palm_size_px):
    """把 21 个像素点合成实心手形(影子剪影):五指链粗圆描边 ∪ 掌心多边形。"""
    stroker = QPainterPathStroker()
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    finger_w = max(4.0, palm_size_px * 0.28)
    palm_w = max(8.0, palm_size_px * 0.55)
    path = QPainterPath()
    for chain in _FINGER_CHAINS:
        line = QPainterPath()
        line.moveTo(QPointF(*points[chain[0]]))
        for idx in chain[1:]:
            line.lineTo(QPointF(*points[idx]))
        stroker.setWidth(palm_w if chain == [0, 17] else finger_w)
        path = path.united(stroker.createStroke(line))
    palm = QPainterPath()
    palm.addPolygon(QPolygonF([QPointF(*points[i]) for i in _PALM_LOOP]))
    palm.closeSubpath()
    return path.united(palm)


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
        self._topmost = False
        self._hand: HandFrame | None = None
        self._scale = 1.0
        self._feedback: str | None = None
        self._feedback_frames = 0
        self._cursor_px = None

    def apply_screen(self) -> None:
        screens = QGuiApplication.screens()
        idx = target_screen_index(self._cfg, screens)
        self.setGeometry(screens[idx].geometry())
        if self._topmost:
            self.show()
            pin_window_topmost(self)
        # 非置顶态保持隐藏,显隐统一由 set_topmost 驱动

    def update_hand(self, hand: HandFrame, scale: float,
                    feedback: str | None, cursor_px=None) -> None:
        self._hand = hand
        self._scale = scale
        self._cursor_px = cursor_px
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
        self._cursor_px = None
        self.update()

    def set_topmost(self, enabled: bool) -> None:
        """启动态置顶显示;非启动态降层并隐藏,彻底不干扰其他窗口。幂等。"""
        if enabled == self._topmost:
            return
        self._topmost = enabled
        if enabled:
            self.show()
            pin_window_topmost(self)
        else:
            unpin_window_topmost(self)
            self.hide()

    def paintEvent(self, event) -> None:
        if self._hand is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pts = scaled_points(self._hand.landmarks, self.width(), self.height(),
                            self._scale)
        if self._cursor_px is not None:
            pts = align_to_cursor(pts, INDEX_TIP, self._cursor_px)
        anchor_idx = INDEX_TIP if self._cursor_px is not None else 0
        pts = fit_hand_to_screen(
            pts, anchor_idx, self.width(), self.height(),
            self._cfg.get("display/hand_max_screen_fraction"))
        palm_px = math.dist(pts[0], pts[9])
        color = QColor(self._cfg.get("display/overlay_color"))
        color.setAlphaF(min(1.0, self._cfg.get("display/overlay_opacity")))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(silhouette_path(pts, palm_px), color)

        if self._feedback:
            wrist = pts[0]
            p.setFont(QFont("", int(28 * self._scale)))
            p.setPen(QColor(0, 0, 0, 230))
            p.drawText(QPointF(wrist[0] + 41, wrist[1] - 39), self._feedback)
            p.setPen(QColor(255, 255, 255, 240))
            p.drawText(QPointF(wrist[0] + 40, wrist[1] - 40), self._feedback)
        p.end()
