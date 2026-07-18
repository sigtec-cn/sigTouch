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


def test_duplicate_labels_take_first():
    first = [(0.2, 0.2, 0.0)] * 21
    assert select_hand([("Right", first), ("Right", _R)], "Right") is first
