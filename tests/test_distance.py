import pytest
from sigtouch.perception.distance import (DistanceSmoother, estimate_distance_m,
                                          focal_px, overlay_scale)


def test_focal_px_640_at_60deg():
    # 640 / (2*tan(30°)) ≈ 554.26
    assert focal_px(640, 60.0) == pytest.approx(554.26, abs=0.1)


def test_estimate_distance_inverse_of_pupil_distance():
    f = focal_px(640, 60.0)
    d1 = estimate_distance_m(58.2, f)   # ≈0.6m
    d2 = estimate_distance_m(29.1, f)   # 瞳距像素减半 → 距离翻倍
    assert d1 == pytest.approx(0.6, abs=0.01)
    assert d2 == pytest.approx(2 * d1, rel=1e-6)


def test_estimate_distance_rejects_nonpositive():
    with pytest.raises(ValueError):
        estimate_distance_m(0.0, 554.0)


def test_smoother_averages_and_holds_on_none():
    s = DistanceSmoother(window=3)
    assert s.update(None) == pytest.approx(0.6)  # 无数据时返回默认
    s.update(1.0)
    s.update(2.0)
    assert s.update(None) == pytest.approx(1.5)  # None 保持既有平均
    assert s.update(3.0) == pytest.approx(2.0)   # (1+2+3)/3


def test_overlay_scale_formula_and_clamp():
    assert overlay_scale(0.6, 24.0) == pytest.approx(1.0)   # 基准
    assert overlay_scale(1.2, 24.0) == pytest.approx(2.0)   # 距离翻倍
    assert overlay_scale(0.6, 48.0) == pytest.approx(0.5)   # 屏幕翻倍
    assert overlay_scale(5.0, 24.0) == pytest.approx(3.0)   # 上限
    assert overlay_scale(0.3, 96.0) == pytest.approx(0.5)   # 下限
