from types import SimpleNamespace

from sigtouch.perception.pipeline import select_primary_face


def _face(span):
    """构造只有虹膜两点有意义的假脸:468/473 水平相距 span(归一化)。"""
    pts = [None] * 478
    pts[468] = SimpleNamespace(x=0.5 - span / 2, y=0.5)
    pts[473] = SimpleNamespace(x=0.5 + span / 2, y=0.5)
    return pts


def test_empty_returns_none():
    assert select_primary_face([]) is None


def test_single_face_selected():
    f = _face(0.05)
    assert select_primary_face([f]) is f


def test_larger_iris_span_wins():
    far, near = _face(0.03), _face(0.09)
    assert select_primary_face([far, near]) is near
    assert select_primary_face([near, far]) is near


def test_tie_takes_first():
    a, b = _face(0.05), _face(0.05)
    assert select_primary_face([a, b]) is a
