import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_apply_theme_installs_global_qss(qapp):
    from sigtouch.ui import theme
    theme.apply_theme(qapp)
    qss = qapp.styleSheet()
    assert theme.ACCENT in qss                    # 主色进入样式表
    assert 'QPushButton[class="primary"]' in qss  # 属性选择器齐备
    assert "QSlider::handle" in qss
    assert 'QFrame[class="card"]' in qss


def test_tokens_are_hex_colors():
    from sigtouch.ui import theme
    for name in ("BG", "CARD", "BORDER", "TEXT", "TEXT_MUTED", "ACCENT",
                 "ACCENT_HOVER", "OK", "WARN", "DANGER"):
        value = getattr(theme, name)
        assert value.startswith("#") and len(value) == 7
