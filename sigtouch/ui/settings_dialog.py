"""设置窗口:四个标签页,控件统一注册到 self._fields,加载/应用走同一条路。"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QLineEdit, QPushButton,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from sigtouch.config import Config


class SettingsDialog(QDialog):
    settings_applied = Signal()

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 设置")
        self._cfg = cfg
        self._fields: dict[str, tuple] = {}  # key -> (widget, getter, setter)

        tabs = QTabWidget()
        tabs.addTab(self._camera_tab(), "摄像头")
        tabs.addTab(self._interaction_tab(), "交互")
        tabs.addTab(self._display_tab(), "显示")
        tabs.addTab(self._general_tab(), "通用")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.Apply)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply)\
               .clicked.connect(self.apply)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self._load()

    # ---- 控件工厂:注册 key → (widget, getter, setter) ----
    def _spin(self, key, lo, hi):
        w = QSpinBox()
        w.setRange(lo, hi)
        self._fields[key] = (w, w.value, w.setValue)
        return w

    def _dspin(self, key, lo, hi, step=0.5, decimals=2):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        self._fields[key] = (w, w.value, w.setValue)
        return w

    def _check(self, key, label=""):
        w = QCheckBox(label)
        self._fields[key] = (w, w.isChecked, w.setChecked)
        return w

    def _monitor_combo(self, key):
        w = QComboBox()
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            w.addItem(f"显示器 {i} ({g.width()}x{g.height()})")
        if w.count() == 0:
            w.addItem("显示器 0")
        self._fields[key] = (w, w.currentIndex, w.setCurrentIndex)
        return w

    def _hand_combo(self, key):
        w = QComboBox()
        w.addItem("右手", "Right")
        w.addItem("左手", "Left")

        def getter():
            return w.currentData()

        def setter(value):
            idx = w.findData(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)

        self._fields[key] = (w, getter, setter)
        return w

    def _color_button(self, key):
        w = QPushButton()

        def getter():
            return w.property("color_hex") or "#000000"

        def setter(value):
            value = str(value)
            w.setProperty("color_hex", value)
            w.setText(value)
            w.setStyleSheet(f"background-color: {value};")

        def pick(_=False):
            from PySide6.QtWidgets import QColorDialog
            c = QColorDialog.getColor(QColor(getter()), self, "选择影子颜色")
            if c.isValid():
                setter(c.name())

        w.clicked.connect(pick)
        self._fields[key] = (w, getter, setter)
        return w

    # ---- 标签页 ----
    def _camera_tab(self):
        page, form = QWidget(), QFormLayout()
        form.addRow("设备索引", self._spin("camera/index", 0, 8))
        form.addRow("画面宽度", self._spin("camera/width", 320, 1920))
        form.addRow("画面高度", self._spin("camera/height", 240, 1080))
        form.addRow("水平视场角(°)", self._dspin("camera/fov_deg", 30.0, 120.0, 1.0, 1))
        page.setLayout(form)
        return page

    def _interaction_tab(self):
        page, form = QWidget(), QFormLayout()
        form.addRow("控制手", self._hand_combo("interaction/active_hand"))
        form.addRow("交互框留白比例", self._dspin("interaction/box_margin", 0.05, 0.30, 0.01))
        form.addRow("平滑截止频率", self._dspin("interaction/smooth_min_cutoff", 0.1, 5.0, 0.1, 1))
        form.addRow("点击最长保持(ms)", self._spin("interaction/click_max_ms", 100, 600))
        form.addRow("OK 停留时长(ms)", self._spin("interaction/ok_hold_ms", 200, 1500))
        form.addRow("手势冷却(ms)", self._spin("interaction/cooldown_ms", 100, 1500))
        form.addRow(self._check("gestures/left_click", "左键(拇指+食指捻)"))
        form.addRow(self._check("gestures/right_click", "右键(拇指+中指捻)"))
        form.addRow(self._check("gestures/scroll", "滚动(三指捻移动)"))
        form.addRow(self._check("gestures/enter", "回车(OK 手势)"))
        form.addRow(self._check("gestures/backspace", "退格(推手)"))
        page.setLayout(form)
        return page

    def _display_tab(self):
        page, form = QWidget(), QFormLayout()
        form.addRow("屏幕对角线(英寸)", self._dspin("display/screen_diag_inch", 10.0, 300.0, 1.0, 1))
        form.addRow("轮廓不透明度", self._dspin("display/overlay_opacity", 0.1, 1.0, 0.05))
        form.addRow("影子颜色", self._color_button("display/overlay_color"))
        form.addRow("目标显示器", self._monitor_combo("display/monitor"))
        page.setLayout(form)
        return page

    def _text(self, key):
        w = QLineEdit()
        self._fields[key] = (w, w.text, w.setText)
        return w

    def _general_tab(self):
        page, form = QWidget(), QFormLayout()
        form.addRow(self._check("general/autostart", "开机自动启动"))
        form.addRow("暂停快捷键", self._text("general/pause_hotkey"))
        page.setLayout(form)
        return page

    # ---- 加载/应用 ----
    def field_widget(self, key):
        return self._fields[key][0]

    def _load(self):
        for key, (_w, _get, set_) in self._fields.items():
            set_(self._cfg.get(key))

    def apply(self):
        for key, (_w, get, _set) in self._fields.items():
            self._cfg.set(key, get())
        self.settings_applied.emit()

    def _ok(self):
        self.apply()
        self.accept()
