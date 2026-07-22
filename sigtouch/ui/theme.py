"""清新浅色主题:设计 token 与全局 QSS。main() 中 apply_theme(app) 一次生效。"""

BG = "#FAFAFA"
CARD = "#FFFFFF"
BORDER = "#E4E4E7"
TEXT = "#09090B"
TEXT_MUTED = "#71717A"
ACCENT = "#18181B"
ACCENT_HOVER = "#27272A"
OK = "#10B981"
WARN = "#F59E0B"
DANGER = "#EF4444"

_QSS = f"""
QDialog {{ background: {BG}; }}
QWidget[class="page"] {{ background: {BG}; }}
QLabel {{ color: {TEXT}; font-size: 13px; background: transparent; }}
QLabel[class="title"] {{ font-size: 17px; font-weight: 600; }}
QLabel[class="subtitle"] {{ font-size: 15px; font-weight: 600; }}
QLabel[class="muted"] {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel[class="grouptitle"] {{ color: {TEXT_MUTED}; font-size: 11px;
    font-weight: 700; letter-spacing: 0.5px; }}
QLabel[class="sliderval"] {{ color: {ACCENT}; font-size: 13px;
    font-weight: 600; }}
QFrame[class="badge-ok"] {{ background: {OK}; border-radius: 9px; }}
QFrame[class="badge-danger"] {{ background: {DANGER}; border-radius: 9px; }}
QPushButton {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 14px; font-size: 13px; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton[class="primary"] {{ background: {ACCENT}; color: white; border: none; }}
QPushButton[class="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[class="primary"]:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}
QPushButton[class="ghost"] {{ background: transparent; border: 1px solid {BORDER};
    color: {TEXT_MUTED}; }}
QPushButton[class="ghost"]:hover {{ border-color: {DANGER}; color: {DANGER}; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{ background: {CARD};
    border: 1px solid {BORDER}; border-radius: 6px; padding: 4px 8px;
    font-size: 13px; color: {TEXT}; }}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border-color: {ACCENT}; }}
QCheckBox {{ color: {TEXT}; font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER};
    border-radius: 4px; background: {CARD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0;
    background: white; border: 2px solid {ACCENT}; border-radius: 8px; }}
QListWidget {{ background: transparent; border: none; font-size: 13px; outline: none; }}
QListWidget::item {{ padding: 10px 12px; border-radius: 6px; margin: 2px 6px;
    color: {TEXT}; }}
QListWidget::item:selected {{ background: {CARD}; color: {ACCENT};
    font-weight: 600; border-left: 3px solid {ACCENT}; }}
QFrame[class="card"] {{ background: {CARD}; border: 1px solid {BORDER};
    border-radius: 8px; }}
QFrame[class="banner-ok"] {{ background: {OK}; border-radius: 8px; }}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(_QSS)


def repolish(widget) -> None:
    """运行时改 class 属性后重新抛光,让属性选择器样式生效。"""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
