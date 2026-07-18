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


def test_align_to_cursor_pins_index_tip():
    from sigtouch.ui.overlay import align_to_cursor
    pts = [(0.0, 0.0), (10.0, 10.0), (20.0, 5.0)]
    out = align_to_cursor(pts, 1, (100.0, 50.0))
    assert out[1] == pytest.approx((100.0, 50.0))   # 食指尖钉在光标上
    assert out[0] == pytest.approx((90.0, 40.0))    # 其余点等量平移
    assert out[2] == pytest.approx((110.0, 45.0))


def test_silhouette_path_covers_fingertips_and_grows():
    import math
    from sigtouch.ui.overlay import silhouette_path
    from tests.hand_fixtures import open_hand
    from PySide6.QtCore import QPointF
    pts = scaled_points(open_hand().landmarks, 1000, 1000, 1.0)
    palm_px = math.dist(pts[0], pts[9])
    path = silhouette_path(pts, palm_px)
    assert not path.isEmpty()
    for tip in (4, 8, 12, 16, 20):                  # 五指尖都在实心手形内
        assert path.contains(QPointF(*pts[tip]))
    thicker = silhouette_path(pts, palm_px * 2)
    assert thicker.boundingRect().width() > path.boundingRect().width()
