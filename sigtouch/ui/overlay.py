"""全屏透明点击穿透覆盖层:Oculus 风格半透明手部轮廓 + 手势进度/反馈图标。"""
import math

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QPainter,
                           QPainterPath, QPainterPathStroker, QPen, QPolygonF)
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QWidget

from sigtouch.config import Config
from sigtouch.interaction.features import INDEX_TIP
from sigtouch.interaction.gestures import GestureProgress
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

    k = max(0.0, min(1.0, k))  # 锚点理论上恒在屏内,防御未来调用方
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


def _stroke_path(path, width: float):
    """把实心路径的轮廓转成指定宽度的描边区域(供辉光逐层外扩)。"""
    stroker = QPainterPathStroker()
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    stroker.setWidth(width)
    outline = QPainterPath()
    outline.addPath(path)
    return stroker.createStroke(outline)


# ---- 手势图标(单位坐标 -1..1 的折线笔画像;绘制时按尺寸缩放) ----
# 每个图标 = 若干"笔",每笔为折线点列表。描画顺序 = 笔顺序 + 笔内点顺序。

# 回车箭头 ↵:第一笔=主干(尾→折角→箭头根),第二笔=箭头两翼
_ENTER_STROKES = [
    [(0.75, -0.70), (0.75, 0.25), (-0.15, 0.25), (-0.70, 0.25)],   # 主干(尾→头)
    [(-0.42, -0.02), (-0.70, 0.25), (-0.42, 0.52)],                # 箭头两翼
]
# 退格:第一笔=左向箭杆+两翼,第二、三笔=×(最后补)
_BACKSPACE_STROKES = [
    [(0.70, 0.0), (-0.45, 0.0)],                                   # 箭杆
    [(-0.20, -0.25), (-0.45, 0.0), (-0.20, 0.25)],                 # 箭头两翼
    [(0.15, -0.18), (0.51, 0.18)],                                 # × 主斜
    [(0.51, -0.18), (0.15, 0.18)],                                 # × 副斜
]
_GESTURE_ICONS = {
    "enter": _ENTER_STROKES,
    "backspace": _BACKSPACE_STROKES,
}


def _strokes_total_length(strokes) -> float:
    return sum(math.dist(a, b) for pts in strokes
               for a, b in zip(pts, pts[1:]))


def _draw_strokes_partial(p: QPainter, strokes, fraction: float,
                          cx: float, cy: float, size: float,
                          width: float, color: QColor) -> None:
    """按 fraction 沿描画顺序部分绘制多笔折线(图标的"逐步填充"进度)。"""
    total = _strokes_total_length(strokes)
    if total <= 0:
        return
    budget = total * max(0.0, min(1.0, fraction))
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for pts in strokes:
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a, b)
            if L <= 0:
                continue
            if budget <= 0:
                return
            r = 1.0 if budget >= L else budget / L
            ax, ay = cx + a[0] * size, cy + a[1] * size
            bx, by = cx + (a[0] + (b[0] - a[0]) * r) * size, \
                     cy + (a[1] + (b[1] - a[1]) * r) * size
            p.drawLine(QPointF(ax, ay), QPointF(bx, by))
            budget -= L


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
        self._progress: GestureProgress | None = None
        self._flash_until = 0          # 触发闪烁截止(monotonic ns)
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
                    progress: GestureProgress | None, cursor_px=None) -> None:
        self._hand = hand
        self._scale = scale
        self._cursor_px = cursor_px
        if progress is not None and progress.fired:
            # 触发帧:记录闪烁窗口(~160ms),进度立即清空避免停留
            self._flash_until = self._now_ns() + 160_000_000
            self._progress = None
        else:
            self._progress = progress
        self.update()

    def clear(self) -> None:
        self._hand = None
        self._progress = None
        self._flash_until = 0
        self._cursor_px = None
        self.update()

    @staticmethod
    def _now_ns() -> int:
        import time
        return time.monotonic_ns()

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
        sil = silhouette_path(pts, palm_px)

        # 亮白辉光:剪影外缘由外到内逐层提亮,暗背景也能看清手影轮廓。
        # 外扩宽度随手掌尺寸缩放,远端小手也有可见光晕。
        glow = self._cfg.get("display/glow_intensity")
        if glow > 0.0:
            base = max(6.0, palm_px * 0.22) * glow
            p.setPen(Qt.PenStyle.NoPen)
            for i, (scale, alpha) in enumerate(
                    ((2.6, 0.10), (1.8, 0.16), (1.2, 0.26), (0.6, 0.42))):
                w = base * scale
                g = QColor(255, 255, 255)
                g.setAlphaF(min(1.0, alpha * glow))
                p.fillPath(_stroke_path(sil, w), g)

        color = QColor(self._cfg.get("display/overlay_color"))
        color.setAlphaF(min(1.0, self._cfg.get("display/overlay_opacity")))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(sil, color)

        # 手势进度与触发闪烁(光标周围)
        self._paint_progress(p, palm_px)
        p.end()

    # ---- 手势进度渲染 ----
    def _paint_progress(self, p: QPainter, palm_px: float) -> None:
        flashing = self._now_ns() < self._flash_until
        prog = self._progress
        if prog is None and not flashing:
            return
        # 进度图标锚点:光标右上方偏移,尺寸随手掌缩放
        cx, cy = (self._cursor_px if self._cursor_px is not None else (0, 0))
        ox, oy = cx + max(28.0, palm_px * 0.5), cy - max(28.0, palm_px * 0.5)
        size = max(14.0, palm_px * 0.32) * self._scale
        accent = QColor(20, 184, 166)          # 主题青
        white = QColor(255, 255, 255)

        if prog is not None:
            kind = prog.kind
            frac = prog.fraction
            if kind in ("left_click", "right_click"):
                self._paint_ring(p, ox, oy, size, frac, accent, white)
            elif kind in _GESTURE_ICONS:
                # 图标描画:淡色底稿 + 按 fraction 高亮填充
                ghost = QColor(white)
                ghost.setAlphaF(0.18)
                _draw_strokes_partial(p, _GESTURE_ICONS[kind], 1.0,
                                      ox, oy, size, size * 0.22, ghost)
                fill = QColor(accent)
                fill.setAlphaF(0.95)
                _draw_strokes_partial(p, _GESTURE_ICONS[kind], frac,
                                      ox, oy, size, size * 0.22, fill)

        if flashing:
            # 触发闪烁:图标位置画一个瞬时高亮圆环放大脉冲
            ring = QRectF(ox - size, oy - size, size * 2, size * 2)
            flash_c = QColor(white)
            flash_c.setAlphaF(0.85)
            pen = QPen(flash_c)
            pen.setWidthF(max(2.0, size * 0.18))
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(ring)

    def _paint_ring(self, p: QPainter, cx: float, cy: float, size: float,
                    frac: float, accent: QColor, white: QColor) -> None:
        """捏合点击:光标周围半透明整圆 + 扇形自顶部顺时针逐步填充。"""
        rect = QRectF(cx - size, cy - size, size * 2, size * 2)
        # 底圈(半透明整圆)
        base = QColor(white)
        base.setAlphaF(0.16)
        pen = QPen(base)
        pen.setWidthF(max(2.0, size * 0.16))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)
        # 扇形进度(从 12 点顺时针,单位 1/16 度)
        fill = QColor(accent)
        fill.setAlphaF(0.9)
        pen2 = QPen(fill)
        pen2.setWidthF(max(2.0, size * 0.16))
        p.setPen(pen2)
        start = 90 * 16
        span = int(-360 * 16 * max(0.0, min(1.0, frac)))
        p.drawArc(rect, start, span)
