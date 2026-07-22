import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from sigtouch.ui.overlay import (_GLYPH_SIZE, _RING_RADIUS, _RING_STROKE,
                                 progress_geometry)


def test_centered_exactly_on_cursor():
    center, radius = progress_geometry((960.0, 540.0))
    assert center == (960.0, 540.0)
    assert radius == _RING_RADIUS


def test_constants_are_fixed_logical_px():
    assert _RING_RADIUS == 22.0
    assert _RING_STROKE == 3.0
    assert _GLYPH_SIZE == 18.0


def test_no_cursor_no_geometry():
    center, radius = progress_geometry(None)
    assert center is None and radius == 0.0
