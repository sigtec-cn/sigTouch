import pytest
from sigtouch.ui.overlay import scaled_points


def _square():
    # 4 个点组成 0.1 见方的正方形,质心 (0.5, 0.5)
    return [(0.45, 0.45, 0.0), (0.55, 0.45, 0.0),
            (0.55, 0.55, 0.0), (0.45, 0.55, 0.0)]


def test_scale_one_maps_normalized_to_pixels():
    pts = scaled_points(_square(), 1000, 500, 1.0)
    assert pts[0] == pytest.approx((450.0, 225.0))
    assert pts[2] == pytest.approx((550.0, 275.0))


def test_scale_two_doubles_span_around_centroid():
    pts = scaled_points(_square(), 1000, 1000, 2.0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert max(xs) - min(xs) == pytest.approx(200.0)  # 原 100px 跨度翻倍
    assert (max(xs) + min(xs)) / 2 == pytest.approx(500.0)  # 质心不动
    assert (max(ys) + min(ys)) / 2 == pytest.approx(500.0)
