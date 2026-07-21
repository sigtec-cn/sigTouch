import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from sigtouch.ui.overlay import fit_hand_to_screen

W, H = 1920, 1080
ANCHOR = 1  # 点 1 作为锚点(模拟食指尖)


def _tall_hand(anchor_xy=(960.0, 540.0), height=540.0):
    """锚点在顶端、主体向下延伸 height 的点集(模拟真实手形)。"""
    ax, ay = anchor_xy
    return [(ax - 100.0, ay), (ax, ay), (ax + 100.0, ay + height)]


def test_oversized_hand_shrinks_to_limit():
    pts = _tall_hand(height=540.0)          # 占屏高 50%
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    ys = [p[1] for p in out]
    assert (max(ys) - min(ys)) == pytest.approx(H * 0.25)


def test_anchor_never_moves():
    pts = _tall_hand(anchor_xy=(300.0, 200.0), height=800.0)
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    assert out[ANCHOR] == pts[ANCHOR]       # 浮点精确相等:光标对齐不被破坏


def test_within_limit_returns_unchanged():
    pts = _tall_hand(height=200.0)          # 已在 25% 限制内
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    assert out == pts


def test_bottom_edge_shrinks_into_screen():
    pts = _tall_hand(anchor_xy=(960.0, 1000.0), height=270.0)  # 会向下出界
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    assert max(p[1] for p in out) <= H + 1e-6                  # 收进屏幕


def test_min_shrink_floors_size_term_away_from_edges():
    # 远离边缘的超大手:尺寸项被下限约束(不会缩到 0.25 目标以下的一半)
    pts = _tall_hand(anchor_xy=(960.0, 50.0), height=1200.0)  # k_size=270/1200=0.225 < 0.5
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25, min_shrink=0.5)
    span = max(p[1] for p in out) - min(p[1] for p in out)
    # 尺寸项被 floor 在 0.5,底部=50+600=650<1080,边缘未约束
    assert span == pytest.approx(600.0)


def test_edge_containment_beats_min_shrink():
    # 超大手贴底边:边缘收容压过下限,完全收进屏幕(可塌缩,食指尖仍在光标上)
    pts = _tall_hand(anchor_xy=(960.0, 1079.0), height=540.0)
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25, min_shrink=0.5)
    assert max(p[1] for p in out) <= H + 1e-6    # 不出界(此前会溢出 269px)
    assert out[ANCHOR] == pts[ANCHOR]            # 锚点不动


def test_degenerate_inputs_do_not_raise():
    flat = [(10.0, 50.0), (20.0, 50.0), (30.0, 50.0)]  # 零高度
    assert fit_hand_to_screen(flat, ANCHOR, W, H, 0.25) == flat
    single = [(5.0, 5.0)]
    assert fit_hand_to_screen(single, 0, W, H, 0.25) == single
