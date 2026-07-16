import pytest
from sigtouch.interaction import features as F
from tests.hand_fixtures import (open_hand, pinch_index, pinch_middle,
                                 three_pinch, ok_pose)


def test_palm_size_is_wrist_to_middle_mcp():
    assert F.palm_size(open_hand()) == pytest.approx(0.10, abs=1e-6)


def test_pinch_ratio_low_when_pinching_high_when_open():
    assert F.pinch_ratio(pinch_index(), F.INDEX_TIP) < 0.35
    assert F.pinch_ratio(open_hand(), F.INDEX_TIP) > 0.55
    assert F.pinch_ratio(pinch_middle(), F.MIDDLE_TIP) < 0.35


def test_pinch_ratio_scale_invariant():
    # 手离摄像头远一倍(scale=0.5),归一化后的比值不变
    near = F.pinch_ratio(pinch_index(scale=1.0), F.INDEX_TIP)
    far = F.pinch_ratio(pinch_index(scale=0.5), F.INDEX_TIP)
    assert near == pytest.approx(far, abs=0.02)


def test_fingers_extended():
    assert F.fingers_extended(open_hand()) == (True, True, True, True)
    idx, mid, ring, pinky = F.fingers_extended(pinch_index())
    assert (mid, ring, pinky) == (False, False, False)
    assert F.fingers_extended(ok_pose())[1:] == (True, True, True)


def test_three_pinch_clusters_three_tips():
    h = three_pinch()
    assert F.pinch_ratio(h, F.INDEX_TIP) < 0.35
    assert F.pinch_ratio(h, F.MIDDLE_TIP) < 0.35
    assert F.fingers_extended(h)[2:] == (False, False)


def test_palm_facing_camera_convention():
    assert F.palm_facing_camera(open_hand(handedness="Right")) is True
    # 镜像翻转 x 得到"手背朝摄像头"的右手
    h = open_hand()
    flipped = type(h)(landmarks=[(1.0 - x, y, z) for x, y, z in h.landmarks],
                      handedness="Right")
    assert F.palm_facing_camera(flipped) is False


def test_bbox_area_grows_with_scale():
    assert F.bbox_area(open_hand(scale=1.3)) > F.bbox_area(open_hand()) * 1.5


def test_anchor_point_between_thumb_and_index():
    ax, ay = F.anchor_point(open_hand())
    assert ax == pytest.approx((0.40 + 0.47) / 2)
    assert ay == pytest.approx((0.49 + 0.40) / 2)
