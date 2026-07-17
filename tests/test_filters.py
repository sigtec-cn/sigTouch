import pytest
from sigtouch.interaction.filters import OneEuroFilter


def test_first_sample_passes_through():
    f = OneEuroFilter()
    assert f.apply(0.42, 0) == pytest.approx(0.42)


def test_constant_input_stays_constant():
    f = OneEuroFilter()
    out = [f.apply(0.5, t) for t in range(0, 1000, 33)]
    assert all(v == pytest.approx(0.5) for v in out)


def test_smoothing_reduces_jitter_amplitude():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    outs = []
    for i, t in enumerate(range(0, 3300, 33)):
        noisy = 0.5 + (0.02 if i % 2 == 0 else -0.02)  # ±0.02 抖动
        outs.append(f.apply(noisy, t))
    tail = outs[30:]
    amplitude = max(tail) - min(tail)
    assert amplitude < 0.02  # 输出抖动 < 输入抖动 0.04 的一半


def test_step_response_moves_toward_target_without_overshoot():
    f = OneEuroFilter()
    f.apply(0.0, 0)
    prev = 0.0
    for t in range(33, 660, 33):
        v = f.apply(1.0, t)
        assert prev - 1e-9 <= v <= 1.0 + 1e-9  # 单调趋近,不过冲
        prev = v
    assert prev > 0.9  # 0.6 秒内基本到位
