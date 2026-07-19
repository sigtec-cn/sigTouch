"""人-屏距离估计(瞳距反推)与手部轮廓缩放。纯 Python。"""
import math
from collections import deque

IPD_M = 0.063          # 成人平均瞳距
REF_DISTANCE_M = 0.6   # 缩放基准:0.6m 处 24 吋屏 scale=1.0
REF_DIAG_INCH = 24.0
SCALE_MIN, SCALE_MAX = 0.5, 5.0
_MIN_SCREEN_DISTANCE_M = 0.05


def focal_px(frame_width_px: int, fov_deg: float) -> float:
    return frame_width_px / (2.0 * math.tan(math.radians(fov_deg) / 2.0))


def estimate_distance_m(pupil_dist_px: float, focal: float,
                        ipd_m: float = IPD_M) -> float:
    if pupil_dist_px <= 0:
        raise ValueError("pupil distance must be positive")
    return focal * ipd_m / pupil_dist_px


class DistanceSmoother:
    """滑动平均;本帧无人脸(None)时沿用历史平均,从未有数据时返回默认值。"""

    def __init__(self, window: int = 15, default_m: float = REF_DISTANCE_M):
        self._buf: deque[float] = deque(maxlen=window)
        self._default = default_m

    def update(self, d: float | None) -> float:
        if d is not None:
            self._buf.append(d)
        if not self._buf:
            return self._default
        return sum(self._buf) / len(self._buf)


def overlay_scale(distance_m: float, diag_inch: float,
                  offset_m: float = 0.0, multiplier: float = 1.0) -> float:
    """轮廓大小(占屏比例)相对基准的倍率:比例 ∝ 人到屏距离 ÷ 屏幕尺寸,再乘用户倍率。

    distance_m 是虹膜法测得的人到摄像头距离;offset_m 是摄像头到屏幕平面的距离
    (摄像头在屏幕前为正),两者之和才是缩放所需的人到屏幕距离。
    """
    d_screen = max(_MIN_SCREEN_DISTANCE_M, distance_m + offset_m)
    raw = (d_screen / REF_DISTANCE_M) * (REF_DIAG_INCH / diag_inch) * multiplier
    return max(SCALE_MIN, min(SCALE_MAX, raw))
