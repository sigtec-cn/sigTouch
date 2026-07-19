# tests/test_select_hand.py
from sigtouch.perception.pipeline import select_hand

_L = [(0.1, 0.1, 0.0)] * 21
_R = [(0.9, 0.9, 0.0)] * 21


def test_selects_matching_hand():
    assert select_hand([("Left", _L), ("Right", _R)], "Right") is _R
    assert select_hand([("Left", _L), ("Right", _R)], "Left") is _L


def test_no_match_returns_none():
    assert select_hand([("Left", _L)], "Right") is None


def test_empty_returns_none():
    assert select_hand([], "Right") is None


def test_duplicate_labels_take_largest_palm():
    def hand(palm_size):
        lms = [(0.5, 0.5, 0.0)] * 21
        lms[9] = (0.5, 0.5 - palm_size, 0.0)  # 腕(0)到中指根(9)的距离即掌尺寸
        return lms

    small, big = hand(0.08), hand(0.15)
    assert select_hand([("Right", small), ("Right", big)], "Right") is big
    assert select_hand([("Right", big), ("Right", small)], "Right") is big  # 与顺序无关
