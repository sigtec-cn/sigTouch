"""One Euro 滤波器 (Casiez et al. 2012):低速强平滑抑抖,高速低延迟跟随。"""
import math


class _LowPass:
    def __init__(self):
        self.last = None

    def apply(self, x: float, alpha: float) -> float:
        self.last = x if self.last is None else alpha * x + (1.0 - alpha) * self.last
        return self.last


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.02,
                 d_cutoff: float = 1.0):
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._d_cutoff = d_cutoff
        self._x = _LowPass()
        self._dx = _LowPass()
        self._t_ms = None

    def apply(self, x: float, t_ms: int) -> float:
        if self._t_ms is None:
            self._t_ms = t_ms
            self._dx.apply(0.0, 1.0)
            return self._x.apply(x, 1.0)
        dt = max((t_ms - self._t_ms) / 1000.0, 1e-3)
        self._t_ms = t_ms
        dx = (x - self._x.last) / dt
        edx = self._dx.apply(dx, _alpha(self._d_cutoff, dt))
        cutoff = self._min_cutoff + self._beta * abs(edx)
        return self._x.apply(x, _alpha(cutoff, dt))
