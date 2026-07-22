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
    from sigtouch.ui.lucide import icon, _SUPERSAMPLE
    for name in NAMES:
        ic = icon(name, size=16)
        assert not ic.isNull(), name
        assert not ic.pixmap(16, 16).isNull(), name
        # Retina 保真:source pixmap 须以 _SUPERSAMPLE 倍物理分辨率保存(不预先降采样
        # 到 16x16),以便高 DPI 屏按 devicePixelRatio 取用时依旧清晰。
        sizes = ic.availableSizes()
        assert sizes, name
        assert sizes[0].width() == 16 * _SUPERSAMPLE, name
        assert sizes[0].height() == 16 * _SUPERSAMPLE, name


def test_unknown_name_raises(qapp):
    from sigtouch.ui.lucide import icon
    with pytest.raises(KeyError):
        icon("no-such-icon")


def test_filled_circle_variant(qapp):
    from sigtouch.ui.lucide import icon
    assert not icon("circle", "#10B981", 12, fill=True).isNull()
