"""交互框→屏幕的光标映射:留白裁剪、平滑滤波(One Euro / 卡尔曼)、捏合冻结。纯 Python。"""
from sigtouch.interaction.filters import KalmanFilter, OneEuroFilter


def _make_filter(algo: str, min_cutoff: float, beta: float,
                 kalman_process: float, kalman_measure: float):
    """按算法名构造单轴滤波器;未知算法回退 One Euro。"""
    if algo == "kalman":
        return KalmanFilter(kalman_process, kalman_measure)
    return OneEuroFilter(min_cutoff, beta)


class CursorMapper:
    def __init__(self, screen_w: int, screen_h: int, margin: float = 0.15,
                 freeze_ms: int = 150, min_cutoff: float = 1.0, beta: float = 0.02,
                 smooth_algo: str = "one_euro",
                 kalman_process: float = 2000.0, kalman_measure: float = 4.0):
        self._w = screen_w
        self._h = screen_h
        self._margin = margin
        self._freeze_ms = freeze_ms
        self._fx = _make_filter(smooth_algo, min_cutoff, beta,
                                kalman_process, kalman_measure)
        self._fy = _make_filter(smooth_algo, min_cutoff, beta,
                                kalman_process, kalman_measure)
        self._freeze_until = -1
        self._was_pinching = False
        self._last: tuple[int, int] | None = None

    def _norm(self, v: float) -> float:
        span = 1.0 - 2.0 * self._margin
        return min(1.0, max(0.0, (v - self._margin) / span))

    def update(self, anchor: tuple[float, float], pinching: bool,
               t_ms: int) -> tuple[int, int]:
        if pinching and not self._was_pinching:
            self._freeze_until = t_ms + self._freeze_ms
        self._was_pinching = pinching

        x = self._fx.apply(self._norm(anchor[0]) * (self._w - 1), t_ms)
        y = self._fy.apply(self._norm(anchor[1]) * (self._h - 1), t_ms)
        if t_ms < self._freeze_until and self._last is not None:
            return self._last  # 冻结期:滤波器照常喂数据,输出保持
        self._last = (round(x), round(y))
        return self._last
