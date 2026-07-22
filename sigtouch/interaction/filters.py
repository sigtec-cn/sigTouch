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


class KalmanFilter:
    """恒定速度卡尔曼滤波(1 维位置):抑抖且高速时不引入明显滞后。

    状态 [pos, vel];过程噪声 q 决定跟随灵敏度(大=更跟手、小=更稳),
    测量噪声 r 决定对手抖/检测噪声的抑制(大=更平滑)。与 OneEuroFilter
    同为 apply(x, t_ms) 接口,可在 CursorMapper 中互换。

    相比 One Euro:卡尔曼显式建模速度,匀速运动时几乎零滞后,且对检测
    抖动(测量噪声)的抑制更稳定;One Euro 在速度突变时响应更快。
    """

    def __init__(self, process_noise: float = 2000.0, measure_noise: float = 4.0):
        self._q = process_noise   # 加速度过程噪声(像素/秒² 量级)
        self._r = measure_noise   # 测量噪声方差(像素²)
        self._x = None            # 位置估计
        self._v = 0.0             # 速度估计
        self._p = [[1.0, 0.0], [0.0, 1.0]]  # 协方差
        self._t_ms = None

    def apply(self, x: float, t_ms: int) -> float:
        if self._t_ms is None:
            self._t_ms = t_ms
            self._x = x
            return x
        dt = (t_ms - self._t_ms) / 1000.0
        self._t_ms = t_ms
        dt = max(dt, 1e-3)

        # 预测:x += v*dt;P = F P Fᵀ + Q
        self._x += self._v * dt
        q = self._q
        p00 = self._p[0][0] + 2 * dt * self._p[1][0] + dt * dt * self._p[1][1] + q * dt ** 4 / 4
        p01 = self._p[0][1] + dt * self._p[1][1] + q * dt ** 3 / 2
        p11 = self._p[1][1] + q * dt * dt
        self._p = [[p00, p01], [p01, p11]]

        # 更新(测量为位置):K = P Hᵀ (H P Hᵀ + R)⁻¹
        s = p00 + self._r
        k0 = p00 / s
        k1 = p01 / s
        innov = x - self._x
        self._x += k0 * innov
        self._v += k1 * innov
        self._p = [[(1 - k0) * p00, (1 - k0) * p01],
                   [-k1 * p00 + p01, -k1 * p01 + p11]]
        return self._x
