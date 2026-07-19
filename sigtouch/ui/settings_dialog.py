"""设置窗口:左导航 + 卡片页 + 即时生效。

_fields 注册表 (key -> (widget, getter, setter)) 与 field_widget()/apply() 兼容保留;
控件变更即时写入 Config:普通键立即发 settings_applied,摄像头组与控制手
进入 500ms 防抖后发 vision_restart_needed(重启视觉线程代价高,合并连续改动)。
"""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QPushButton, QSlider,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from sigtouch.config import DEFAULTS, Config

_RESTART_KEYS = frozenset({
    "camera/index", "camera/width", "camera/height", "camera/fov_deg",
    "interaction/active_hand",
})
_DEBOUNCE_MS = 500
_NAV_ITEMS = ["📷 摄像头", "✋ 交互", "🎨 显示", "⚙️ 通用"]


class SettingsDialog(QDialog):
    settings_applied = Signal()        # 轻量键即时生效
    vision_restart_needed = Signal()   # 摄像头组/控制手:防抖后重启视觉线程

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 设置")
        self.setFixedSize(660, 480)
        self._cfg = cfg
        self._fields: dict[str, tuple] = {}
        self._loading = False

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.setInterval(_DEBOUNCE_MS)
        self._restart_timer.timeout.connect(self.vision_restart_needed)

        nav = QListWidget()
        nav.setFixedWidth(140)
        nav.addItems(_NAV_ITEMS)
        self._stack = QStackedWidget()
        for build in (self._camera_page, self._interaction_page,
                      self._display_page, self._general_page):
            self._stack.addWidget(build())
        nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        nav.setCurrentRow(0)

        restore = QPushButton("恢复默认")
        restore.clicked.connect(self._restore_defaults)
        close = QPushButton("关闭")
        close.setProperty("class", "primary")
        close.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addWidget(restore)
        bottom.addStretch(1)
        bottom.addWidget(close)

        body = QHBoxLayout()
        body.addWidget(nav)
        body.addWidget(self._stack, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 16, 12)
        layout.addLayout(body, 1)
        layout.addLayout(bottom)
        self._load()

    # ---- 页面骨架 ----
    def _page(self, title: str) -> tuple:
        """返回 (page_widget, form_layout):标题 + 白卡片内表单。"""
        page = QWidget()
        page.setProperty("class", "page")
        v = QVBoxLayout(page)
        v.setContentsMargins(16, 8, 4, 8)
        head = QLabel(title)
        head.setProperty("class", "subtitle")
        v.addWidget(head)
        card = QFrame()
        card.setProperty("class", "card")
        form = QFormLayout(card)
        form.setContentsMargins(16, 12, 16, 12)
        form.setVerticalSpacing(6)
        v.addWidget(card)
        v.addStretch(1)
        return page, form

    def _row(self, form: QFormLayout, label: str, widget, desc: str) -> None:
        form.addRow(label, widget)
        hint = QLabel(desc)
        hint.setProperty("class", "muted")
        hint.setWordWrap(True)
        form.addRow("", hint)

    # ---- 控件工厂(注册 + 即时生效接线)----
    def _on_field_changed(self, key: str) -> None:
        if self._loading:
            return
        _w, getter, _s = self._fields[key]
        self._cfg.set(key, getter())
        if key in _RESTART_KEYS:
            self._restart_timer.start()
        else:
            self.settings_applied.emit()

    def _spin(self, key, lo, hi):
        w = QSpinBox()
        w.setRange(lo, hi)
        self._fields[key] = (w, w.value, w.setValue)
        w.valueChanged.connect(lambda _v, k=key: self._on_field_changed(k))
        return w

    def _dspin(self, key, lo, hi, step=0.5, decimals=2):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        self._fields[key] = (w, w.value, w.setValue)
        w.valueChanged.connect(lambda _v, k=key: self._on_field_changed(k))
        return w

    def _check(self, key, label=""):
        w = QCheckBox(label)
        self._fields[key] = (w, w.isChecked, w.setChecked)
        w.toggled.connect(lambda _v, k=key: self._on_field_changed(k))
        return w

    def _text(self, key):
        w = QLineEdit()
        self._fields[key] = (w, w.text, w.setText)
        w.editingFinished.connect(lambda k=key: self._on_field_changed(k))
        return w

    def _slider(self, key, lo, hi, to_cfg, from_cfg, fmt):
        """整数滑杆 + 实时数值;to_cfg(int)->存储值, from_cfg(存储值)->int。"""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        w = QSlider(Qt.Orientation.Horizontal)
        w.setRange(lo, hi)
        val = QLabel()
        val.setFixedWidth(44)
        w.valueChanged.connect(lambda v: val.setText(fmt(v)))
        h.addWidget(w, 1)
        h.addWidget(val)
        self._fields[key] = (w, lambda: to_cfg(w.value()),
                             lambda stored: w.setValue(from_cfg(stored)))
        w.valueChanged.connect(lambda _v, k=key: self._on_field_changed(k))
        return box

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
        w.currentIndexChanged.connect(lambda _i, k=key: self._on_field_changed(k))
        return w

    def _monitor_combo(self, key):
        w = QComboBox()
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            w.addItem(f"显示器 {i} ({g.width()}x{g.height()})")
        if w.count() == 0:
            w.addItem("显示器 0")
        self._fields[key] = (w, w.currentIndex, w.setCurrentIndex)
        w.currentIndexChanged.connect(lambda _i, k=key: self._on_field_changed(k))
        return w

    def _color_button(self, key):
        w = QPushButton()

        def getter():
            return w.property("color_hex") or "#000000"

        def setter(value):
            value = str(value)
            w.setProperty("color_hex", value)
            w.setText(value)
            w.setStyleSheet(f"background-color: {value}; color: white;")

        def pick(_=False):
            from PySide6.QtWidgets import QColorDialog
            c = QColorDialog.getColor(QColor(getter()), self, "选择影子颜色")
            if c.isValid():
                setter(c.name())
                self._on_field_changed(key)

        w.clicked.connect(pick)
        self._fields[key] = (w, getter, setter)
        return w

    # ---- 四页 ----
    def _camera_page(self):
        page, form = self._page("摄像头")
        self._row(form, "设备索引", self._spin("camera/index", 0, 8),
                  "多摄像头时选择设备;改动约半秒后自动重启识别")
        self._row(form, "画面宽度", self._spin("camera/width", 320, 1920),
                  "更高分辨率更准但更耗 CPU")
        self._row(form, "画面高度", self._spin("camera/height", 240, 1080), "")
        self._row(form, "水平视场角(°)",
                  self._dspin("camera/fov_deg", 30.0, 120.0, 1.0, 1),
                  "用于估算你与屏幕的距离,普通摄像头约 60°")
        return page

    def _interaction_page(self):
        page, form = self._page("交互")
        self._row(form, "控制手", self._hand_combo("interaction/active_hand"),
                  "只有选定的这只手可以控制鼠标")
        self._row(form, "边缘留白",
                  self._slider("interaction/box_margin", 5, 30,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"),
                  "交互框四边留白,越大手臂移动越省力")
        self._row(form, "跟手程度",
                  self._slider("interaction/smooth_min_cutoff", 1, 50,
                               lambda v: v / 10.0,
                               lambda s: round(float(s) * 10),
                               lambda v: f"{v/10:.1f}"),
                  "越低越平滑,越高越跟手")
        self._row(form, "点击最长保持(ms)",
                  self._spin("interaction/click_max_ms", 100, 600),
                  "捏合超过该时长视为拖拽")
        self._row(form, "OK 停留时长(ms)",
                  self._spin("interaction/ok_hold_ms", 200, 1500), "")
        self._row(form, "手势冷却(ms)",
                  self._spin("interaction/cooldown_ms", 100, 1500), "")
        for key, label in (("gestures/left_click", "左键(拇指+食指捻)"),
                           ("gestures/right_click", "右键(拇指+中指捻)"),
                           ("gestures/scroll", "滚动(三指捻移动)"),
                           ("gestures/enter", "回车(OK 手势)"),
                           ("gestures/backspace", "退格(推手)")):
            form.addRow(self._check(key, label))
        return page

    def _display_page(self):
        page, form = self._page("显示")
        self._row(form, "屏幕对角线(英寸)",
                  self._dspin("display/screen_diag_inch", 10.0, 300.0, 1.0, 1),
                  "屏幕越大或人越远,手部影子按比例放大")
        self._row(form, "影子不透明度",
                  self._slider("display/overlay_opacity", 10, 100,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"), "")
        self._row(form, "影子颜色", self._color_button("display/overlay_color"),
                  "深色背景下可改浅色提高可见度")
        self._row(form, "目标显示器", self._monitor_combo("display/monitor"), "")
        return page

    def _general_page(self):
        page, form = self._page("通用")
        self._row(form, "", self._check("general/autostart", "开机自动启动"), "")
        self._row(form, "暂停快捷键", self._text("general/pause_hotkey"),
                  "pynput 组合键语法,留空禁用;默认 Ctrl+Alt+P")
        return page

    # ---- 加载/应用/恢复 ----
    def field_widget(self, key):
        return self._fields[key][0]

    def _load(self):
        self._loading = True
        try:
            for key, (_w, _get, set_) in self._fields.items():
                set_(self._cfg.get(key))
        finally:
            self._loading = False

    def apply(self):
        """全量写回(恢复默认与测试用);保留原 settings_applied 语义。"""
        for key, (_w, get, _set) in self._fields.items():
            self._cfg.set(key, get())
        self.settings_applied.emit()

    def _restore_defaults(self):
        self._loading = True
        try:
            for key in self._fields:
                self._cfg.set(key, DEFAULTS[key])
            self._load()
        finally:
            self._loading = False
        self.settings_applied.emit()
        self._restart_timer.start()
