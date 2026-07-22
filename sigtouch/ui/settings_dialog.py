"""设置窗口:左导航 + 分组卡片页 + 即时生效。

_fields 注册表 (key -> (widget, getter, setter)) 与 field_widget()/apply() 兼容保留;
控件变更即时写入 Config:普通键立即发 settings_applied,摄像头组与控制手
进入 500ms 防抖后发 vision_restart_needed(重启视觉线程代价高,合并连续改动)。

布局约定:每页若干"分组卡片"(带小标题),控件用表单对齐;相关项聚成一组,
滑杆右侧实时数值;描述文字淡色小字置底。整体留白、对齐、层级比 v1.3 更清晰。
"""
import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                               QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QSlider, QSpinBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from sigtouch.config import DEFAULTS, Config
from sigtouch.interaction.hotkey import format_hotkey
from sigtouch.ui import lucide, theme

_RESTART_KEYS = frozenset({
    "camera/index", "camera/width", "camera/height", "camera/fov_deg",
    "interaction/active_hand",
})
_DEBOUNCE_MS = 500
_APPLY_DEBOUNCE_MS = 200
_NAV_ITEMS = ["摄像头", "交互", "显示", "通用"]
_NAV_ICONS = ["camera", "hand", "palette", "settings"]


class SettingsDialog(QDialog):
    settings_applied = Signal()        # 轻量键即时生效
    vision_restart_needed = Signal()   # 摄像头组/控制手:防抖后重启视觉线程

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 设置")
        self.setMinimumSize(680, 620)
        self.resize(700, 640)
        self._cfg = cfg
        self._fields: dict[str, tuple] = {}
        self._loading = False

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.setInterval(_DEBOUNCE_MS)
        self._restart_timer.timeout.connect(self.vision_restart_needed)

        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(_APPLY_DEBOUNCE_MS)
        self._apply_timer.timeout.connect(self.settings_applied)

        # 顶部状态卡
        status_card = QFrame()
        status_card.setProperty("class", "card")
        sv = QVBoxLayout(status_card)
        sv.setContentsMargins(16, 12, 16, 12)
        sv.setSpacing(3)
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.setSpacing(6)
        self._status_icon = QLabel()
        badge_row.addWidget(self._status_icon)
        self._status_badge = QLabel()
        self._status_badge.setStyleSheet("font-weight: 600; background: transparent;")
        badge_row.addWidget(self._status_badge)
        badge_row.addStretch(1)
        sv.addLayout(badge_row)
        self._hotkey_line = QLabel()
        self._hotkey_line.setProperty("class", "muted")
        sv.addWidget(self._hotkey_line)

        nav = QListWidget()
        nav.setFixedWidth(148)
        for text, icon_name in zip(_NAV_ITEMS, _NAV_ICONS):
            item = QListWidgetItem(lucide.icon(icon_name, theme.TEXT, 16), text)
            nav.addItem(item)
        self._stack = QStackedWidget()
        for build in (self._camera_page, self._interaction_page,
                      self._display_page, self._general_page):
            self._stack.addWidget(build())
        nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        nav.setCurrentRow(0)

        restore = QPushButton("恢复默认")
        restore.setProperty("class", "ghost")
        restore.clicked.connect(self._restore_defaults)
        close = QPushButton("完成")
        close.setProperty("class", "primary")
        close.setDefault(True)
        close.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.setContentsMargins(2, 4, 2, 0)
        bottom.addWidget(restore)
        bottom.addStretch(1)
        bottom.addWidget(close)

        body = QHBoxLayout()
        body.setSpacing(6)
        body.addWidget(nav)
        body.addWidget(self._stack, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(status_card)
        layout.addLayout(body, 1)
        layout.addLayout(bottom)
        self._load()
        self.set_running_state("active")
        self.refresh_hotkey_label()

    # ---- 页面骨架 ----
    def _page(self) -> "tuple[QWidget, QVBoxLayout]":
        """返回 (page_widget, 页垂直布局);分组卡片经 _group() 加入。"""
        page = QWidget()
        page.setProperty("class", "page")
        v = QVBoxLayout(page)
        v.setContentsMargins(14, 6, 2, 8)
        v.setSpacing(12)
        v.addStretch(1)  # 底部弹簧,分组卡片靠上对齐
        return page, v

    def _group(self, page_layout: "QVBoxLayout", title: str) -> "QFormLayout":
        """在页内插入一个分组卡片(小标题 + 表单),返回表单布局。插到弹簧前。"""
        card = QFrame()
        card.setProperty("class", "card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(16, 12, 16, 14)
        cv.setSpacing(4)
        if title:
            head = QLabel(title)
            head.setProperty("class", "grouptitle")
            cv.addWidget(head)
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setVerticalSpacing(8)
        form.setHorizontalSpacing(18)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        cv.addLayout(form)
        page_layout.insertWidget(page_layout.count() - 1, card)
        return form

    def _row(self, form: QFormLayout, label: str, widget, desc: str = "") -> None:
        form.addRow(label, widget)
        if desc:
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
        # 用户手填屏幕尺寸即视为已确认,不再自动提示
        if key == "display/screen_diag_inch":
            self._cfg.set("display/screen_diag_detected", True)
        if key in _RESTART_KEYS:
            self._restart_timer.start()
        else:
            self._apply_timer.start()
        if key == "general/pause_hotkey":
            self.refresh_hotkey_label()

    def _spin(self, key, lo, hi):
        w = QSpinBox()
        w.setRange(lo, hi)
        self._fields[key] = (w, w.value, w.setValue)
        w.valueChanged.connect(lambda _v, k=key: self._on_field_changed(k))
        return w

    def _dspin(self, key, lo, hi, step=0.5, decimals=2, suffix=""):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        if suffix:
            w.setSuffix(suffix)
        self._fields[key] = (w, w.value, w.setValue)
        w.valueChanged.connect(lambda _v, k=key: self._on_field_changed(k))
        return w

    def _check(self, key, label=""):
        w = QCheckBox(label)
        self._fields[key] = (w, w.isChecked, w.setChecked)
        w.toggled.connect(lambda _v, k=key: self._on_field_changed(k))
        return w

    def _text(self, key, placeholder=""):
        w = QLineEdit()
        if placeholder:
            w.setPlaceholderText(placeholder)
        self._fields[key] = (w, w.text, w.setText)
        w.editingFinished.connect(lambda k=key: self._on_field_changed(k))
        return w

    def _slider(self, key, lo, hi, to_cfg, from_cfg, fmt):
        """整数滑杆 + 实时数值;to_cfg(int)->存储值, from_cfg(存储值)->int。"""
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        w = QSlider(Qt.Orientation.Horizontal)
        w.setRange(lo, hi)
        val = QLabel()
        val.setFixedWidth(52)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val.setProperty("class", "sliderval")
        val.setText(fmt(w.value()))
        w.valueChanged.connect(lambda v: val.setText(fmt(v)))
        h.addWidget(w, 1)
        h.addWidget(val)
        self._fields[key] = (w, lambda: to_cfg(w.value()),
                             lambda stored: w.setValue(from_cfg(stored)))
        w.valueChanged.connect(lambda _v, k=key: self._on_field_changed(k))
        return box

    def _combo(self, key, items):
        """items: [(显示文本, data), ...];getter 返回 currentData。"""
        w = QComboBox()
        for text, data in items:
            w.addItem(text, data)

        def getter():
            return w.currentData()

        def setter(value):
            idx = w.findData(value)
            w.setCurrentIndex(idx if idx >= 0 else 0)

        self._fields[key] = (w, getter, setter)
        w.currentIndexChanged.connect(lambda _i, k=key: self._on_field_changed(k))
        return w

    def _hand_combo(self, key):
        return self._combo(key, [("右手", "Right"), ("左手", "Left")])

    def _monitor_combo(self, key):
        w = QComboBox()
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            w.addItem(f"显示器 {i}  ·  {g.width()}×{g.height()}")
        if w.count() == 0:
            w.addItem("显示器 0")
        self._fields[key] = (w, w.currentIndex, w.setCurrentIndex)
        w.currentIndexChanged.connect(lambda _i, k=key: self._on_field_changed(k))
        return w

    def _color_button(self, key):
        w = QPushButton()
        w.setFixedHeight(30)

        def getter():
            return w.property("color_hex") or "#000000"

        def setter(value):
            value = str(value)
            w.setProperty("color_hex", value)
            w.setText(value)
            hexval = value.lstrip("#")
            r, g, b = (int(hexval[i:i + 2], 16) for i in (0, 2, 4))
            luminance = r * 0.299 + g * 0.587 + b * 0.114
            text_color = "black" if luminance > 140 else "white"
            w.setStyleSheet(f"background-color: {value}; color: {text_color};"
                            " border-radius: 6px; border: 1px solid rgba(0,0,0,0.15);")

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
        page, v = self._page()
        f = self._group(v, "采集设备")
        self._row(f, "设备索引", self._spin("camera/index", 0, 8),
                  "多摄像头时选择设备;改动约半秒后自动重启识别")
        f2 = self._group(v, "画面")
        self._row(f2, "宽度", self._spin("camera/width", 320, 1920),
                  "更高分辨率更准但更耗 CPU")
        self._row(f2, "高度", self._spin("camera/height", 240, 1080), "")
        self._row(f2, "水平视场角",
                  self._dspin("camera/fov_deg", 30.0, 120.0, 1.0, 1, " °"),
                  "用于估算你与屏幕的距离,普通摄像头约 60°")
        return page

    def _interaction_page(self):
        page, v = self._page()
        f = self._group(v, "控制")
        self._row(f, "控制手", self._hand_combo("interaction/active_hand"),
                  "只有选定的这只手可以控制鼠标")
        self._row(f, "边缘留白",
                  self._slider("interaction/box_margin", 5, 30,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"),
                  "交互框四边留白,越大手臂移动越省力")

        fs = self._group(v, "平滑(抑抖)")
        self._row(fs, "算法",
                  self._combo("interaction/smooth_algo",
                              [("卡尔曼滤波(推荐)", "kalman"),
                               ("One Euro", "one_euro")]),
                  "卡尔曼匀速更稳、几乎无滞后;One Euro 变向响应更快")
        self._row(fs, "稳定程度",
                  self._slider("interaction/kalman_measure", 1, 20,
                               lambda v: float(v),
                               lambda s: round(float(s)),
                               lambda v: f"{v}"),
                  "卡尔曼:越大越平滑、抑制手抖越强(跟手略降)")
        self._row(fs, "响应速度",
                  self._slider("interaction/kalman_process", 200, 8000,
                               lambda v: float(v),
                               lambda s: round(float(s)),
                               lambda v: f"{v}"),
                  "卡尔曼:越大越跟手;抖动明显可调低")
        self._row(fs, "跟手程度",
                  self._slider("interaction/smooth_min_cutoff", 1, 50,
                               lambda v: v / 10.0,
                               lambda s: round(float(s) * 10),
                               lambda v: f"{v/10:.1f}"),
                  "One Euro:越低越平滑,越高越跟手")

        fg = self._group(v, "手势判定时间")
        self._row(fg, "捏合点击",
                  self._slider("interaction/pinch_hold_ms", 500, 3000,
                               lambda v: float(v),
                               lambda s: round(float(s)),
                               lambda v: f"{v/1000:.1f}s"),
                  "捏合按住到该时长才触发点击,光标周围圆环显示进度")
        self._row(fg, "竖大拇指",
                  self._slider("interaction/thumbs_up_hold_ms", 500, 3000,
                               lambda v: float(v),
                               lambda s: round(float(s)),
                               lambda v: f"{v/1000:.1f}s"),
                  "竖起大拇指保持该时长触发回车")
        self._row(fg, "拇指向左",
                  self._slider("interaction/thumbs_left_hold_ms", 500, 3000,
                               lambda v: float(v),
                               lambda s: round(float(s)),
                               lambda v: f"{v/1000:.1f}s"),
                  "拇指握拳向左保持该时长触发退格")

        fg2 = self._group(v, "手势开关")
        for key, label in (("gestures/left_click", "左键(拇指+食指捏合按住)"),
                           ("gestures/right_click", "右键(拇指+中指捏合按住)"),
                           ("gestures/scroll", "滚动(三指捻移动)"),
                           ("gestures/enter", "回车(竖大拇指)"),
                           ("gestures/backspace", "退格(拇指向左)")):
            fg2.addRow(self._check(key, label))
        self._row(fg2, "手势冷却",
                  self._spin("interaction/cooldown_ms", 100, 1500),
                  "同一手势触发后的最短间隔,防连发")
        return page

    def _display_page(self):
        page, v = self._page()
        f = self._group(v, "屏幕")
        self._row(f, "目标显示器", self._monitor_combo("display/monitor"), "")
        self._row(f, "屏幕对角线",
                  self._dspin("display/screen_diag_inch", 10.0, 300.0, 0.5, 1, " 英寸"),
                  "启动时自动检测;检测不到请手动填写,影响手影物理大小")
        self._row(f, "摄像头到屏幕距离",
                  self._dspin("display/camera_screen_offset_m", -2.0, 10.0, 0.1, 1, " m"),
                  "摄像头装在屏幕前方时填正值;0 表示摄像头就在屏幕平面(如笔记本)")

        fa = self._group(v, "手影外观")
        self._row(fa, "不透明度",
                  self._slider("display/overlay_opacity", 10, 100,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"), "")
        self._row(fa, "颜色", self._color_button("display/overlay_color"),
                  "深色背景下可改浅色提高可见度")
        self._row(fa, "边缘辉光",
                  self._slider("display/glow_intensity", 0, 200,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"),
                  "手影外圈的亮白光晕,暗背景下更清晰;0 关闭")

        fz = self._group(v, "手影大小")
        self._row(fz, "大小倍率",
                  self._slider("display/hand_scale_multiplier", 50, 300,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"),
                  "物理模型算完后的整体微调,大屏看不清就调大")
        self._row(fz, "最大高度",
                  self._slider("display/hand_max_screen_fraction", 10, 60,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"),
                  "手影高度上限(占屏幕高度比例);超过时自动收缩并收进屏幕")
        return page

    def _general_page(self):
        page, v = self._page()
        f = self._group(v, "快捷键")
        self._row(f, "暂停 / 恢复",
                  self._text("general/pause_hotkey", "<ctrl>+<alt>+p"),
                  "pynput 组合键语法,留空禁用;默认 Ctrl+Alt+P")
        self._row(f, "打开设置",
                  self._text("general/settings_hotkey", "<ctrl>+<alt>+s"),
                  "唤起本设置窗口的全局快捷键,留空禁用;默认 Ctrl+Alt+S")

        fs = self._group(v, "系统")
        self._row(fs, "", self._check("general/autostart", "开机自动启动"), "")
        return page

    # ---- 状态卡 ----
    _STATE_TEXT = {
        "active": ("使用中", theme.OK),
        "paused": ("已暂停(摄像头已关闭)", theme.TEXT_MUTED),
        "permission": ("等待权限授权", theme.WARN),
        "error": ("摄像头异常", theme.DANGER),
    }

    def set_running_state(self, state: str) -> None:
        text, color = self._STATE_TEXT.get(state, self._STATE_TEXT["active"])
        self._status_badge.setText(text)
        self._status_badge.setStyleSheet(
            f"color: {color}; font-weight: 600; background: transparent;")
        self._status_icon.setPixmap(
            lucide.icon("circle", color, 10, fill=True).pixmap(10, 10))

    def refresh_hotkey_label(self) -> None:
        key = format_hotkey(self._cfg.get("general/pause_hotkey"))
        skey = format_hotkey(self._cfg.get("general/settings_hotkey"))
        self._hotkey_line.setText(
            f"暂停/恢复:<b>{html.escape(key)}</b>    "
            f"打开设置:<b>{html.escape(skey)}</b>(在「通用」页可修改)")

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
                if key == "display/screen_diag_detected":
                    continue
                self._cfg.set(key, DEFAULTS[key])
            self._load()
            self.refresh_hotkey_label()
        finally:
            self._loading = False
        self.settings_applied.emit()
        self._restart_timer.start()
