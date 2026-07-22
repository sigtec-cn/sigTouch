import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

NAMES = ["camera", "hand", "palette", "settings", "mouse-pointer", "keyboard",
         "check", "x", "triangle-alert", "rotate-cw", "video", "shield",
         "power", "circle", "pause", "play"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_all_icons_render_nonnull(qapp):
    from sigtouch.ui.lucide import icon
    for name in NAMES:
        ic = icon(name)
        assert not ic.isNull(), name
        assert not ic.pixmap(16, 16).isNull(), name


def test_unknown_name_raises(qapp):
    from sigtouch.ui.lucide import icon
    with pytest.raises(KeyError):
        icon("no-such-icon")


def test_filled_circle_variant(qapp):
    from sigtouch.ui.lucide import icon
    assert not icon("circle", "#10B981", 12, fill=True).isNull()
