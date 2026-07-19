# SigTouch v1.3 实现计划:UI 视觉与交互刷新

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清新浅色 QSS 主题;设置窗左导航+卡片+滑杆+即时生效;权限窗卡片化;托盘/预览美化;应用图标资产。

**Architecture:** 新增 `ui/theme.py`(token+全局 QSS,main() 应用一次);设置窗重构但保留 `_fields` 注册表与 `field_widget()/apply()` 兼容层,新增 `vision_restart_needed` 防抖信号;app 把 `_on_settings_applied` 拆为 `_apply_light_settings` 与 `_on_vision_restart_needed`;权限窗仅改布局层(行为契约不动);图标资产由脚本生成后入库。

**Tech Stack:** 现有栈;Pillow 仅 dev extra(生成图标资产,构建机不需要)。

**Spec:** `docs/superpowers/specs/2026-07-19-ui-refresh-design.md`

## Global Constraints

- GUI 只能用 PySide6;纯度约束不变(interaction/types/distance 不碰)。
- 兼容红线:`_fields` 结构 `(widget, getter, setter)`、`field_widget(key)`、`apply()`(全量写回工具)、wizard 的 `checker/requester/opener` 注入与 `all_granted` 升沿语义、`_status_labels/_request_buttons/_open_buttons/_timer/_was_all_granted` 属性名、`make_icon(color_hex)` 签名——全部保留。
- 即时生效规则:`_RESTART_KEYS = {camera/index, camera/width, camera/height, camera/fov_deg, interaction/active_hand}` 走 500ms 单次防抖 → `vision_restart_needed`;其余键立即 `settings_applied`;程序化 `_load()` 期间(`self._loading=True`)一律不触发。
- QSS 属性选择器控件(class 属性)在运行时改 class 后必须 unpolish/polish 重新抛光。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`(基线 85);提交前缀规范同前,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 文件结构总览

```
sigtouch/ui/theme.py                 # 新增:token + apply_theme(Task 1)
sigtouch/app.py                      # main() 应用主题(Task 1);信号拆分(Task 4)
tests/test_theme.py                  # 新增(Task 1)
sigtouch/ui/icons.py                 # 托盘图标重绘(Task 2)
sigtouch/ui/tray.py                  # 菜单 emoji 文案(Task 2)
sigtouch/ui/preview.py               # 深色画布(Task 2)
tests/test_permission_wizard.py      # 托盘菜单断言适配(Task 2);徽章断言适配(Task 5)
sigtouch/ui/settings_dialog.py       # 重构(Task 3)
tests/test_settings_dialog.py        # 适配(Task 3)
tests/test_settings_instant.py       # 新增(Task 3)
tests/test_app_frame_path.py         # _apply_light_settings 更名适配(Task 4)
tests/test_app_permissions.py        # 双路径测试(Task 4)
sigtouch/ui/permission_wizard.py     # 卡片化(Task 5)
scripts/generate_icons.py assets/    # 图标资产(Task 6)
packaging/sigtouch.spec pyproject.toml docs/manual-qa.md  # (Task 6)
```

---

### Task 1: 主题系统

**Files:**
- Create: `sigtouch/ui/theme.py`
- Modify: `sigtouch/app.py`(main() 内 QApplication 后应用)
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces: token 常量 `BG/CARD/BORDER/TEXT/TEXT_MUTED/ACCENT/ACCENT_HOVER/OK/WARN/DANGER` 与 `apply_theme(app) -> None`。后续任务用 `widget.setProperty("class", "primary"|"muted"|"title"|"subtitle"|"badge-ok"|"badge-danger"|"card"|"banner-ok")` 挂样式。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_theme.py
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
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_theme.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 2: 实现 theme.py**

```python
# sigtouch/ui/theme.py
"""清新浅色主题:设计 token 与全局 QSS。main() 中 apply_theme(app) 一次生效。"""

BG = "#F7F9FA"
CARD = "#FFFFFF"
BORDER = "#E3E8EB"
TEXT = "#1F2933"
TEXT_MUTED = "#6B7680"
ACCENT = "#14B8A6"
ACCENT_HOVER = "#0D9488"
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
QLabel[class="badge-ok"] {{ background: {OK}; color: white;
    border-radius: 9px; padding: 2px 10px; font-size: 12px; }}
QLabel[class="badge-danger"] {{ background: {DANGER}; color: white;
    border-radius: 9px; padding: 2px 10px; font-size: 12px; }}
QPushButton {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 14px; font-size: 13px; }}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton[class="primary"] {{ background: {ACCENT}; color: white; border: none; }}
QPushButton[class="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[class="primary"]:disabled {{ background: {BORDER}; color: {TEXT_MUTED}; }}
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
```

- [ ] **Step 3: main() 应用主题**

`sigtouch/app.py` 的 `main()`,`app.setApplicationName("SigTouch")` 之后插入:

```python
    from sigtouch.ui.theme import apply_theme
    apply_theme(app)
```

- [ ] **Step 4: 回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 85 + 2 = 87

```bash
git add sigtouch/ui/theme.py sigtouch/app.py tests/test_theme.py
git commit -m "feat: fresh light theme tokens and global QSS"
```

---

### Task 2: 托盘图标重绘、菜单文案与预览深色画布

**Files:**
- Modify: `sigtouch/ui/icons.py`, `sigtouch/ui/tray.py`, `sigtouch/ui/preview.py`, `tests/test_permission_wizard.py`(托盘菜单断言)

**Interfaces:**
- `make_icon(color_hex) -> QIcon` 签名不变(内部改画:状态色圆底 + 白色简化手掌)。
- `_STATE_META` 切换文案:active→"⏸ 暂停"、paused→"▶ 恢复"、error/permission→"⏸ 暂停";菜单项:"⚙️ 设置…"、"🔐 权限设置…"、"🎥 调试预览"、"⏻ 退出"。

- [ ] **Step 1: 更新托盘菜单断言(先失败)**

`tests/test_permission_wizard.py` 的 `test_tray_permission_state_and_menu` 中:

```python
    texts = [a.text() for a in t._menu.actions()]
    assert any("权限设置" in x for x in texts)   # 原为 "权限设置…" in texts
```

- [ ] **Step 2: 实现三处修改**

`icons.py` 的 `make_icon` 函数体替换:

```python
def make_icon(color_hex: str) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color_hex))
    p.drawEllipse(2, 2, 60, 60)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(20, 30, 24, 22)                      # 掌
    for x, h in ((14, 14), (22, 18), (30, 20), (38, 18), (46, 13)):
        p.drawRoundedRect(x, 34 - h, 6, h, 3, 3)       # 五指圆头短柱
    p.end()
    return QIcon(pm)
```

`tray.py`:`_STATE_META` 替换为:

```python
_STATE_META = {
    "active": (COLOR_ACTIVE, "SigTouch:运行中", "⏸ 暂停"),
    "paused": (COLOR_PAUSED, "SigTouch:已暂停", "▶ 恢复"),
    "error": (COLOR_ERROR, "SigTouch:摄像头异常", "⏸ 暂停"),
    "permission": (COLOR_PERMISSION, "SigTouch:等待权限授权", "⏸ 暂停"),
}
```

菜单构造中四个文案改为 `"⏸ 暂停"`(初始 toggle)、`"⚙️ 设置…"`、`"🔐 权限设置…"`、`"🎥 调试预览"`、`"⏻ 退出"`。

`preview.py` 的 `__init__` 中 `self._label` 创建后追加:

```python
        self.setStyleSheet("background: #101418;")
        layout.setContentsMargins(0, 0, 0, 0)
        self.resize(800, 620)
```

(`layout` 即现有 QVBoxLayout 变量。)

- [ ] **Step 3: 回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 87 全过

```bash
git add sigtouch/ui/icons.py sigtouch/ui/tray.py sigtouch/ui/preview.py \
        tests/test_permission_wizard.py
git commit -m "feat: refined tray icon, emoji menu labels and dark preview canvas"
```

---

### Task 3: 设置窗口重构(导航+卡片+滑杆+即时生效)

**Files:**
- Modify: `sigtouch/ui/settings_dialog.py`(整体重写)、`tests/test_settings_dialog.py`(小适配)
- Test: `tests/test_settings_instant.py`(新增)

**Interfaces:**
- Produces: `SettingsDialog(cfg, parent=None)`,信号 `settings_applied`(轻量键即时发)与 **新增** `vision_restart_needed`(camera/*、interaction/active_hand 防抖 500ms 后发);`field_widget(key)`、`apply()`、`_fields` 兼容保留;新增 `_restore_defaults()`、`_restart_timer`(QTimer 单次 500ms)。Task 4 消费两个信号。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_settings_instant.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dlg(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    return SettingsDialog(Config(backend={}))


def test_light_key_applies_immediately_and_signals(qapp):
    dlg = _dlg(qapp)
    got = []
    dlg.settings_applied.connect(lambda: got.append(1))
    dlg.field_widget("display/overlay_opacity").setValue(80)  # 滑杆 80%
    assert dlg._cfg.get("display/overlay_opacity") == pytest.approx(0.80)
    assert got == [1]                                   # 立即发且只发一次
    assert dlg._restart_timer.isActive() is False       # 轻量键不碰重启防抖


def test_restart_key_debounces_single_signal(qapp):
    dlg = _dlg(qapp)
    fired = []
    dlg.vision_restart_needed.connect(lambda: fired.append(1))
    dlg.field_widget("camera/index").setValue(1)
    dlg.field_widget("camera/index").setValue(2)        # 连续两次改动
    assert dlg._cfg.get("camera/index") == 2            # 配置即时写入
    assert fired == [] and dlg._restart_timer.isActive()
    dlg._restart_timer.stop()
    dlg._restart_timer.timeout.emit()                   # 模拟防抖到期
    assert fired == [1]                                 # 合并为一次


def test_load_does_not_emit_signals(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    cfg = Config(backend={"camera/index": 2})
    got = []
    dlg = SettingsDialog(cfg)                           # 构造期 _load 不触发
    dlg.settings_applied.connect(lambda: got.append("a"))
    dlg.vision_restart_needed.connect(lambda: got.append("v"))
    dlg._load()                                         # 显式重载同样安静
    assert got == []


def test_restore_defaults_reverts_and_applies(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("camera/index").setValue(3)
    dlg.field_widget("display/overlay_opacity").setValue(90)
    assert dlg._cfg.get("camera/index") == 3
    dlg._restore_defaults()
    assert dlg._cfg.get("camera/index") == 0
    assert dlg._cfg.get("display/overlay_opacity") == pytest.approx(0.35)
    assert dlg._restart_timer.isActive() is True        # 默认值可能改了摄像头组 → 走防抖


def test_slider_mappings(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("interaction/box_margin").setValue(20)
    assert dlg._cfg.get("interaction/box_margin") == pytest.approx(0.20)
    dlg.field_widget("interaction/smooth_min_cutoff").setValue(25)
    assert dlg._cfg.get("interaction/smooth_min_cutoff") == pytest.approx(2.5)
```

同时适配 `tests/test_settings_dialog.py`:三个既有测试保持语义,唯一必要调整——若断言前需要干净信号状态,保持现有写法即可(既有测试的 `settings_applied` connect 都发生在控件修改之后,不受即时发射影响);`apply()` 仍应发一次 `settings_applied`(保留原语义)。

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_instant.py -v`
Expected: FAIL(无 vision_restart_needed / 滑杆控件)

- [ ] **Step 2: 重写 settings_dialog.py**

```python
# sigtouch/ui/settings_dialog.py
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
```

- [ ] **Step 3: 运行确认通过 + 全量回归**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`
Expected: 87 + 5 = 92(既有 test_settings_dialog 三项照常通过;若 `test_dialog_loads_defaults_and_applies_changes` 因 `_load` 顺序失败,核对 `_loading` 守卫而非改断言)

- [ ] **Step 4: 提交**

```bash
git add sigtouch/ui/settings_dialog.py tests/test_settings_dialog.py \
        tests/test_settings_instant.py
git commit -m "feat: sidebar settings with sliders, hints and instant apply"
```

---

### Task 4: app 双路径接线

**Files:**
- Modify: `sigtouch/app.py`, `tests/test_app_frame_path.py`(方法更名), `tests/test_app_permissions.py`(新增双路径测试)

**Interfaces:**
- Produces: `_apply_light_settings()`(原 `_on_settings_applied` 去掉 `_restart_vision()` 的其余全部)与 `_on_vision_restart_needed()`(轻量应用 + `_restart_vision()`);`__init__` 接线 `settings_applied → _apply_light_settings`、`vision_restart_needed → _on_vision_restart_needed`。

- [ ] **Step 1: 写失败测试(追加到 tests/test_app_permissions.py)**

```python
def test_light_settings_do_not_restart_vision(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    monkeypatch.setattr(
        "sigtouch.platformsupport.autostart.set_autostart", lambda *_: None)
    a = _make_app(monkeypatch)
    restarts = []
    monkeypatch.setattr(a, "_restart_vision", lambda: restarts.append(1))
    a._apply_light_settings()
    assert restarts == []            # 轻量路径不重启视觉线程
    a._on_vision_restart_needed()
    assert restarts == [1]           # 重启路径走 _restart_vision
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_app_permissions.py -v`
Expected: FAIL(`AttributeError: _apply_light_settings`)

- [ ] **Step 2: 修改 app.py**

`_on_settings_applied` 整体替换为两个方法(内容与原方法一致,仅拆分;`release_all` 前置与 autostart 同步保留在轻量路径):

```python
    def _apply_light_settings(self) -> None:
        """设置即时生效的轻量路径:不重启视觉线程。"""
        if self._injector is not None:
            self._injector.release_all()  # 拖拽中重建交互对象前释放
        from sigtouch.platformsupport.autostart import set_autostart
        try:
            set_autostart(self._cfg.get("general/autostart"))
        except OSError:
            _log.warning("开机自启设置失败", exc_info=True)
        self._build_interaction()
        self._overlay.apply_screen()
        self._setup_hotkey()

    def _on_vision_restart_needed(self) -> None:
        """摄像头组/控制手改动:轻量应用 + 重启视觉线程。"""
        self._apply_light_settings()
        self._restart_vision()
```

`__init__` 中 `self._settings_dlg.settings_applied.connect(self._on_settings_applied)` 替换为:

```python
        self._settings_dlg.settings_applied.connect(self._apply_light_settings)
        self._settings_dlg.vision_restart_needed.connect(
            self._on_vision_restart_needed)
```

`tests/test_app_frame_path.py`:`test_settings_applied_mid_drag_releases_button` 中的 `a._on_settings_applied()` 调用改为 `a._apply_light_settings()`(断言不变)。

- [ ] **Step 3: 回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 92 + 1 = 93

```bash
git add sigtouch/app.py tests/test_app_frame_path.py tests/test_app_permissions.py
git commit -m "feat: split settings apply into light and vision-restart paths"
```

---

### Task 5: 权限引导窗卡片化

**Files:**
- Modify: `sigtouch/ui/permission_wizard.py`, `tests/test_permission_wizard.py`(徽章断言)

**Interfaces:**
- 行为契约不变:`checker/requester/opener` 注入、`refresh()`、`all_granted` 升沿一次、timer 生命周期、属性名 `_status_labels/_request_buttons/_open_buttons/_timer/_was_all_granted/_banner`。
- 徽章文案:「✓ 已授权」/「✗ 未授权」(class badge-ok/badge-danger + repolish)。

- [ ] **Step 1: 更新测试断言(先失败)**

`tests/test_permission_wizard.py`:

```python
    # test_missing_permission_rendered_and_buttons_wired 中:
    assert w._status_labels[K.CAMERA].text().startswith("✓")
    assert w._status_labels[K.ACCESSIBILITY].text().startswith("✗")
    # test_all_granted_emitted_once_on_rising_edge 末行:
    assert w._status_labels[K.ACCESSIBILITY].text().startswith("✓")
```

- [ ] **Step 2: 重写 wizard 布局层**

```python
# sigtouch/ui/permission_wizard.py
"""权限引导窗:卡片式逐项状态 + 主动请求 + 打开系统设置,自动轮询刷新。
布局为 v1.3 卡片化;行为契约(注入依赖/升沿信号/timer 生命周期)与 v1.1 一致。"""
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout)

from sigtouch.platformsupport import permissions as perms
from sigtouch.platformsupport.permissions import PermissionKind
from sigtouch.ui.theme import repolish

_ROWS = [
    (PermissionKind.CAMERA, "📷", "摄像头", "识别手部与人脸(核心功能)"),
    (PermissionKind.ACCESSIBILITY, "🖱️", "辅助功能", "控制鼠标与键盘(手势注入)"),
    (PermissionKind.INPUT_MONITORING, "⌨️", "输入监控", "全局暂停快捷键"),
]
_POLL_MS = 2000
_CLOSE_DELAY_MS = 2000


class PermissionWizard(QDialog):
    all_granted = Signal()

    def __init__(self, checker=None, requester=None, opener=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 权限设置")
        self.setFixedWidth(520)
        self._checker = checker
        self._requester = requester
        self._opener = opener
        self._was_all_granted = False
        self._status_labels: dict[PermissionKind, QLabel] = {}
        self._request_buttons: dict[PermissionKind, QPushButton] = {}
        self._open_buttons: dict[PermissionKind, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        title = QLabel("SigTouch 权限设置")
        title.setProperty("class", "title")
        layout.addWidget(title)
        sub = QLabel("SigTouch 需要以下系统权限。授权后无需重启,应用会自动激活。")
        sub.setProperty("class", "muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self._banner = QFrame()
        self._banner.setProperty("class", "banner-ok")
        btext = QLabel("✓ 全部权限已就绪,SigTouch 已自动激活")
        btext.setStyleSheet("color: white; font-weight: 600; background: transparent;")
        bl = QHBoxLayout(self._banner)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.addWidget(btext)
        self._banner.setVisible(False)
        layout.addWidget(self._banner)

        for kind, icon, name, why in _ROWS:
            card = QFrame()
            card.setProperty("class", "card")
            grid = QGridLayout(card)
            grid.setContentsMargins(14, 10, 14, 10)
            ic = QLabel(icon)
            ic.setStyleSheet("font-size: 22px; background: transparent;")
            grid.addWidget(ic, 0, 0, 2, 1)
            head = QLabel(f"<b>{name}</b>")
            grid.addWidget(head, 0, 1)
            badge = QLabel()
            self._status_labels[kind] = badge
            grid.addWidget(badge, 0, 2, alignment=None)
            hint = QLabel(why)
            hint.setProperty("class", "muted")
            grid.addWidget(hint, 1, 1, 1, 2)
            req = QPushButton("请求权限")
            req.setProperty("class", "primary")
            req.clicked.connect(lambda _=False, k=kind: self._request(k))
            self._request_buttons[kind] = req
            grid.addWidget(req, 0, 3, 2, 1)
            opn = QPushButton("打开系统设置")
            opn.clicked.connect(lambda _=False, k=kind: self._open(k))
            self._open_buttons[kind] = opn
            grid.addWidget(opn, 0, 4, 2, 1)
            layout.addWidget(card)
        layout.addStretch(1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(_POLL_MS)
        self.refresh()

    def _snapshot(self) -> dict:
        return self._checker() if self._checker else perms.snapshot()

    def _request(self, kind: PermissionKind) -> None:
        (self._requester or perms.request)(kind)

    def _open(self, kind: PermissionKind) -> None:
        (self._opener or perms.open_settings)(kind)

    def refresh(self) -> None:
        snap = self._snapshot()
        for kind, badge in self._status_labels.items():
            ok = bool(snap.get(kind, True))
            badge.setText("✓ 已授权" if ok else "✗ 未授权")
            badge.setProperty("class", "badge-ok" if ok else "badge-danger")
            repolish(badge)
            self._request_buttons[kind].setEnabled(not ok)
        granted = all(snap.values())
        self._banner.setVisible(granted)
        if granted:
            self._timer.stop()
        if granted and not self._was_all_granted:
            self.all_granted.emit()
            QTimer.singleShot(_CLOSE_DELAY_MS, self.close)
        self._was_all_granted = granted

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        if not self._was_all_granted:
            self._timer.start(_POLL_MS)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()
```

(注意保留 v1.1 修复语义:granted → timer.stop;show 未就绪重启轮询;hide 停。原 `_banner.setText` 逻辑由 `setVisible` 取代。)

- [ ] **Step 3: 回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 93 全过

```bash
git add sigtouch/ui/permission_wizard.py tests/test_permission_wizard.py
git commit -m "feat: card-style permission wizard with status badges"
```

---

### Task 6: 应用图标资产与打包接线

**Files:**
- Create: `scripts/generate_icons.py`, `assets/icon.icns`, `assets/icon.ico`(脚本产物,提交入库)
- Modify: `pyproject.toml`(dev extra + pillow), `packaging/sigtouch.spec`, `docs/manual-qa.md`

- [ ] **Step 1: pyproject dev extra 加 pillow 并安装**

`dev = [...]` 列表追加 `"pillow>=10.0",`;Run: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 2: 写生成脚本并运行**

```python
# scripts/generate_icons.py
"""生成应用图标资产(青绿圆底 + 白色手掌,与托盘图标同族)。
本地运行一次,产物提交入库,构建机不需要 Pillow:
    .venv/bin/python scripts/generate_icons.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (20, 184, 166, 255)   # #14B8A6
WHITE = (255, 255, 255, 255)
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def draw_master(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size * 0.04
    d.ellipse([m, m, size - m, size - m], fill=ACCENT)
    s = size / 64.0  # 与托盘 64px 几何同族
    d.ellipse([20 * s, 30 * s, 44 * s, 52 * s], fill=WHITE)
    for x, h in ((14, 14), (22, 18), (30, 20), (38, 18), (46, 13)):
        d.rounded_rectangle([x * s, (34 - h) * s, (x + 6) * s, 34 * s],
                            radius=3 * s, fill=WHITE)
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    master = draw_master()
    master.save(ASSETS / "icon.ico",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                       (128, 128), (256, 256)])
    print("wrote", ASSETS / "icon.ico")
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as td:
            iconset = Path(td) / "icon.iconset"
            iconset.mkdir()
            for sz in (16, 32, 64, 128, 256, 512):
                master.resize((sz, sz)).save(iconset / f"icon_{sz}x{sz}.png")
                master.resize((sz * 2, sz * 2)).save(
                    iconset / f"icon_{sz}x{sz}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset),
                            "-o", str(ASSETS / "icon.icns")], check=True)
        print("wrote", ASSETS / "icon.icns")


if __name__ == "__main__":
    main()
```

Run: `.venv/bin/python scripts/generate_icons.py`
Expected: `assets/icon.ico` 与 `assets/icon.icns` 生成(icns 约几百 KB)

- [ ] **Step 3: spec 挂图标**

`packaging/sigtouch.spec`:文件顶部加 `import sys as _sys`;`EXE(...)` 增加参数 `icon="../assets/icon.ico" if _sys.platform == "win32" else None,`;`BUNDLE(...)` 增加参数 `icon="../assets/icon.icns",`。

- [ ] **Step 4: 本地构建验证**

Run: `rm -rf build dist && .venv/bin/pyinstaller packaging/sigtouch.spec`
Expected: 构建成功;`ls dist/SigTouch.app/Contents/Resources/ | grep -i icns` 有图标文件;`plutil -p dist/SigTouch.app/Contents/Info.plist | grep -i CFBundleIconFile` 非空。

- [ ] **Step 5: manual-qa 第 13 项 + 回归 + 提交**

`docs/manual-qa.md` 追加:

```markdown
13. (v1.3)UI 观感走查:设置窗左侧导航切换流畅、滑杆拖动数值实时更新且立即生效
    (改不透明度立刻反映在影子上)、改摄像头设备约半秒后自动重启识别;「恢复默认」
    一键还原;权限窗为卡片式且徽章状态正确;托盘图标为圆底手掌样式、菜单带图标;
    Dock/资源管理器中应用图标为青绿手掌(非默认空白)。
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q` → 93
Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"`(未改动,防回归确认)

```bash
git add scripts/generate_icons.py assets/ pyproject.toml packaging/sigtouch.spec \
        docs/manual-qa.md
git commit -m "feat: app icon assets and packaging integration"
```

---

## 最终验收清单

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` 全部通过(预期 93)。
2. 分支推送后 CI 三平台全绿。
3. 本地 .app 构建含图标(Task 6 Step 4)。
4. 人工 QA:`docs/manual-qa.md` 第 13 项走查。
5. 纯度 grep 与 PyQt grep 为空。

## 后续工作(不在本计划)

- 深色模式;动画过渡;Linux 托盘特化。

