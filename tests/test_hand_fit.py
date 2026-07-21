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


def test_min_shrink_floor_keeps_hand_visible():
    # 锚点贴最底边:任何收缩都无法完全收进 → 触及下限 0.5,但仍可见
    pts = _tall_hand(anchor_xy=(960.0, 1079.0), height=540.0)
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25, min_shrink=0.5)
    span = max(p[1] for p in out) - min(p[1] for p in out)
    assert span > 0                                    # 未塌缩
    assert span >= (H * 0.25) * 0.5 - 1e-6             # 不低于 尺寸限制×下限


def test_degenerate_inputs_do_not_raise():
    flat = [(10.0, 50.0), (20.0, 50.0), (30.0, 50.0)]  # 零高度
    assert fit_hand_to_screen(flat, ANCHOR, W, H, 0.25) == flat
    single = [(5.0, 5.0)]
    assert fit_hand_to_screen(single, 0, W, H, 0.25) == single
