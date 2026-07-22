# tests/test_thumbs_up.py — is_thumbs_up 几何判定
from sigtouch.interaction import features as F
from tests.hand_fixtures import (open_hand, ok_pose, pinch_index,
                                 pinch_middle, three_pinch, thumbs_up)


def test_thumbs_up_detected():
    assert F.is_thumbs_up(thumbs_up()) is True


def test_open_hand_not_thumbs_up():
    assert F.is_thumbs_up(open_hand()) is False  # 四指伸直


def test_ok_pose_not_thumbs_up():
    assert F.is_thumbs_up(ok_pose()) is False  # 三指伸直


def test_pinch_not_thumbs_up():
    assert F.is_thumbs_up(pinch_index()) is False
    assert F.is_thumbs_up(pinch_middle()) is False
    assert F.is_thumbs_up(three_pinch()) is False
