# SigTouch v1.2 实现计划:桌面 App、影子渲染与光标锚定

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** macOS 打包 .app;影子置顶所有窗口;光标锚定食指且影子跟随光标;设置左/右手;深色剪影渲染替代骨架。

**Architecture:** 锚点与选手逻辑改动在纯函数层(features/pipeline);渲染改动集中在 overlay(新增 align_to_cursor / silhouette_path 纯函数 + cursor_px 参数);原生置顶收进新模块 ui/native.py(fail-open);app 只加一处传参和 raise 兜底;打包在 spec 追加 BUNDLE。

**Tech Stack:** 现有栈 + `pyobjc-framework-Cocoa`(仅 darwin)。

**Spec:** `docs/superpowers/specs/2026-07-18-desktop-app-and-shadow-design.md`

## Global Constraints

- GUI 只能用 PySide6;`sigtouch/interaction/`、`perception/types.py`、`perception/distance.py` 纯度约束不变。
- 原生置顶与一切平台增强 fail-open:异常仅 `logging.warning`,不影响运行。
- `OverlayWindow.update_hand` 的 `cursor_px` 参数必须带默认值 `None`(None 时不平移,保持旧行为)——保证任务间套件始终绿。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`(基线 75);提交前缀 feat/fix/test/chore/docs,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 镜像画面下 MediaPipe handedness 标签视为与真实手一致(调试预览显示标签,真机若反向由 manual-qa 揭示后修映射)。

## 文件结构总览

```
sigtouch/interaction/features.py     # anchor_point → 食指尖(Task 1)
tests/test_features.py               # 锚点断言更新(Task 1)
sigtouch/config.py                   # +interaction/active_hand;overlay_color 默认改 #000000(Task 2 / Task 4)
sigtouch/perception/pipeline.py      # select_hand + num_hands=2 + active_hand(Task 2)
sigtouch/vision.py                   # 传 active_hand(Task 2)
sigtouch/ui/preview.py               # 显示 hand=标签(Task 2)
tests/test_select_hand.py            # 新增(Task 2)
sigtouch/ui/settings_dialog.py       # 控制手下拉 + 影子颜色按钮(Task 3)
tests/test_settings_dialog.py        # roundtrip 扩展(Task 3)
sigtouch/ui/native.py                # pin_window_topmost(Task 4)
sigtouch/ui/overlay.py               # 剪影渲染 + align_to_cursor + cursor_px(Task 4)
pyproject.toml                       # +pyobjc-framework-Cocoa(Task 4)
tests/test_overlay_geometry.py       # align/silhouette 单测(Task 4)
sigtouch/app.py                      # cursor_px 传参 + watchdog raise(Task 5)
tests/test_app_permissions.py        # overlay 传参断言(Task 5)
packaging/sigtouch.spec              # BUNDLE(Task 6)
.github/workflows/release.yml        # macOS 打包 .app(Task 6)
README.md packaging/README.md docs/manual-qa.md  # 文档(Task 6)
```

---

### Task 1: 光标锚点改为食指指尖

**Files:**
- Modify: `sigtouch/interaction/features.py`, `tests/test_features.py`

**Interfaces:**
- Produces: `anchor_point(hand) -> tuple[float, float]` 语义变更为**食指指尖**归一化坐标。消费方(mapper 经 app 调用)无签名变化。

- [ ] **Step 1: 更新测试(先失败)**

`tests/test_features.py` 中删除 `test_anchor_point_between_thumb_and_index`,替换为:

```python
def test_anchor_point_is_index_fingertip():
    ax, ay = F.anchor_point(open_hand())
    assert ax == pytest.approx(0.47)   # 基准张开手食指尖 x
    assert ay == pytest.approx(0.40)   # 基准张开手食指尖 y
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_features.py -v`
Expected: 新测试 FAIL(现实现返回拇指食指中点)

- [ ] **Step 2: 修改 features.anchor_point**

```python
def anchor_point(hand: HandFrame) -> tuple[float, float]:
    """光标锚点:食指指尖——光标始终钉在影子的食指上。"""
    x, y, _ = hand.landmarks[INDEX_TIP]
    return (x, y)
```

- [ ] **Step 3: 全量回归**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`
Expected: 75 全过(其余测试不依赖锚点具体值;若有失败逐一核对是否为对锚点坐标的隐性依赖,修测试预期而非产品码)

- [ ] **Step 4: 提交**

```bash
git add sigtouch/interaction/features.py tests/test_features.py
git commit -m "feat: anchor cursor to index fingertip"
```

---

### Task 2: 左右手选择(感知层)

**Files:**
- Modify: `sigtouch/config.py`, `sigtouch/perception/pipeline.py`, `sigtouch/vision.py`, `sigtouch/ui/preview.py`
- Test: `tests/test_select_hand.py`

**Interfaces:**
- Produces: `DEFAULTS["interaction/active_hand"] = "Right"`;`pipeline.select_hand(hands: list[tuple[str, list]], wanted: str) -> list | None`(模块级纯函数);`PerceptionPipeline(frame_width, fov_deg, models_dir=None, active_hand="Right")`。Task 3 的设置控件与此 key 绑定;设置 Apply 走既有 `_restart_vision()` 即时生效。

- [ ] **Step 1: config 增加默认值**

`DEFAULTS` 的 interaction 段追加:

```python
    "interaction/active_hand": "Right",  # 控制手:"Right" | "Left"
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_select_hand.py
from sigtouch.perception.pipeline import select_hand

_L = [(0.1, 0.1, 0.0)] * 21
_R = [(0.9, 0.9, 0.0)] * 21


def test_selects_matching_hand():
    assert select_hand([("Left", _L), ("Right", _R)], "Right") is _R
    assert select_hand([("Left", _L), ("Right", _R)], "Left") is _L


def test_no_match_returns_none():
    assert select_hand([("Left", _L)], "Right") is None


def test_empty_returns_none():
    assert select_hand([], "Right") is None


def test_duplicate_labels_take_first():
    first = [(0.2, 0.2, 0.0)] * 21
    assert select_hand([("Right", first), ("Right", _R)], "Right") is first
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_select_hand.py -v`
Expected: FAIL(`ImportError: select_hand`)

- [ ] **Step 3: 实现**

`pipeline.py` 模块级(class 之前)加:

```python
def select_hand(hands, wanted):
    """从 [(handedness_label, landmarks), ...] 中取第一只 label==wanted 的手;无匹配返回 None。"""
    for label, lms in hands:
        if label == wanted:
            return lms
    return None
```

`PerceptionPipeline.__init__` 签名加 `active_hand: str = "Right"`,存 `self._active_hand = active_hand`;`HandLandmarkerOptions` 的 `num_hands=1` 改为 `num_hands=2`。

`process()` 的手部段替换为:

```python
        hand = None
        hres = self._hands.detect_for_video(image, t_ms)
        if hres.hand_landmarks:
            candidates = [
                (hres.handedness[i][0].category_name,
                 [(p.x, p.y, p.z) for p in lms])
                for i, lms in enumerate(hres.hand_landmarks)
            ]
            picked = select_hand(candidates, self._active_hand)
            if picked is not None:
                hand = HandFrame(landmarks=picked,
                                 handedness=self._active_hand)
```

`vision.py` 构造管线处改为:

```python
            pipeline = PerceptionPipeline(
                self._cfg.get("camera/width"),
                self._cfg.get("camera/fov_deg"),
                active_hand=self._cfg.get("interaction/active_hand"))
```

`preview.py` 在 `pinch=` 文本之后追加一行手性标签:

```python
            cv2.putText(bgr, f"hand={r.hand.handedness}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
```

- [ ] **Step 4: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 75 + 4 = 79

```bash
git add sigtouch/config.py sigtouch/perception/pipeline.py sigtouch/vision.py \
        sigtouch/ui/preview.py tests/test_select_hand.py
git commit -m "feat: single-hand control filtered by configurable handedness"
```

---

### Task 3: 设置界面——控制手下拉与影子颜色按钮

**Files:**
- Modify: `sigtouch/ui/settings_dialog.py`, `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: `interaction/active_hand`(Task 2)、`display/overlay_color`(既有)。
- Produces: 交互页首行"控制手"下拉(右手/Right、左手/Left,经 userData 映射);显示页"影子颜色"按钮(点击弹 QColorDialog,`_fields` 存 hex 字符串)。均走既有 `_fields` 注册表。

- [ ] **Step 1: 写失败测试(追加到 tests/test_settings_dialog.py)**

```python
def test_active_hand_and_color_roundtrip(qapp):
    from sigtouch.ui.settings_dialog import SettingsDialog
    cfg = Config(backend={})
    dlg = SettingsDialog(cfg)
    # 默认加载
    hand_widget = dlg.field_widget("interaction/active_hand")
    assert hand_widget.currentData() == "Right"
    color_widget = dlg.field_widget("display/overlay_color")
    # 修改并应用(setter 经注册表,与 _load 同路)
    dlg._fields["interaction/active_hand"][2]("Left")
    dlg._fields["display/overlay_color"][2]("#112233")
    dlg.apply()
    assert cfg.get("interaction/active_hand") == "Left"
    assert cfg.get("display/overlay_color") == "#112233"
    assert color_widget.text() == "#112233"
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_dialog.py -v`
Expected: 新测试 FAIL(`KeyError: interaction/active_hand`)

- [ ] **Step 2: 实现两个控件工厂**

`settings_dialog.py` import 区补 `QPushButton` 与 `from PySide6.QtGui import QColor`;控件工厂区追加:

```python
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
```

`_interaction_tab` 的 form 首行插入:

```python
        form.addRow("控制手", self._hand_combo("interaction/active_hand"))
```

`_display_tab` 在"轮廓不透明度"之后插入:

```python
        form.addRow("影子颜色", self._color_button("display/overlay_color"))
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 79 + 1 = 80

```bash
git add sigtouch/ui/settings_dialog.py tests/test_settings_dialog.py
git commit -m "feat: active-hand selector and shadow color picker in settings"
```

---

### Task 4: 剪影渲染、光标对齐与原生置顶

**Files:**
- Create: `sigtouch/ui/native.py`
- Modify: `sigtouch/ui/overlay.py`, `sigtouch/config.py`, `pyproject.toml`
- Test: `tests/test_overlay_geometry.py`(追加)

**Interfaces:**
- Produces:
  - `native.pin_window_topmost(widget) -> None`(非 darwin no-op;darwin 设 NSWindow level/collectionBehavior;fail-open)。
  - overlay 模块级纯函数 `align_to_cursor(points, index_tip_idx: int, cursor_px: tuple) -> list[tuple]`、`silhouette_path(points, palm_size_px: float) -> QPainterPath`。
  - `OverlayWindow.update_hand(hand, scale, feedback, cursor_px=None)`(**默认 None 保持旧行为**,Task 5 才传值)。
  - `DEFAULTS["display/overlay_color"]` 改为 `"#000000"`。

- [ ] **Step 1: pyproject 增加 Cocoa 依赖并安装**

`[project].dependencies` 追加:

```toml
    "pyobjc-framework-Cocoa>=10.0; sys_platform == 'darwin'",
```

Run: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 2: 写失败测试(追加到 tests/test_overlay_geometry.py)**

```python
def test_align_to_cursor_pins_index_tip():
    from sigtouch.ui.overlay import align_to_cursor
    pts = [(0.0, 0.0), (10.0, 10.0), (20.0, 5.0)]
    out = align_to_cursor(pts, 1, (100.0, 50.0))
    assert out[1] == pytest.approx((100.0, 50.0))   # 食指尖钉在光标上
    assert out[0] == pytest.approx((90.0, 40.0))    # 其余点等量平移
    assert out[2] == pytest.approx((110.0, 45.0))


def test_silhouette_path_covers_fingertips_and_grows():
    import math
    from sigtouch.ui.overlay import silhouette_path
    from tests.hand_fixtures import open_hand
    from PySide6.QtCore import QPointF
    pts = scaled_points(open_hand().landmarks, 1000, 1000, 1.0)
    palm_px = math.dist(pts[0], pts[9])
    path = silhouette_path(pts, palm_px)
    assert not path.isEmpty()
    for tip in (4, 8, 12, 16, 20):                  # 五指尖都在实心手形内
        assert path.contains(QPointF(*pts[tip]))
    thicker = silhouette_path(pts, palm_px * 2)
    assert thicker.boundingRect().width() > path.boundingRect().width()
```

(若 QPainterPath 构造在无 QGuiApplication 时报错,在文件顶部按 test_settings_dialog.py 的方式补 offscreen QApplication fixture。)

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_overlay_geometry.py -v`
Expected: 新测试 FAIL(`ImportError`)

- [ ] **Step 3: 实现 native.py**

```python
# sigtouch/ui/native.py
"""平台原生窗口增强。非 macOS 一律 no-op;任何失败 fail-open 仅记日志。"""
import logging
import sys

_log = logging.getLogger(__name__)

# NSWindowCollectionBehavior 位标志
_CAN_JOIN_ALL_SPACES = 1 << 0
_STATIONARY = 1 << 4
_FULLSCREEN_AUXILIARY = 1 << 8
_SCREEN_SAVER_LEVEL = 1000  # NSScreenSaverWindowLevel:高于全屏窗口层


def pin_window_topmost(widget) -> None:
    """把 Qt 窗口提升到所有窗口(含全屏 App)之上并跟随所有空间。仅 macOS 有实际动作。"""
    if sys.platform != "darwin":
        return
    try:
        import objc  # pyobjc-framework-Cocoa
        from ctypes import c_void_p

        ns_view = objc.objc_object(c_void_p=c_void_p(int(widget.winId())))
        ns_window = ns_view.window()
        if ns_window is None:
            return
        ns_window.setLevel_(_SCREEN_SAVER_LEVEL)
        ns_window.setCollectionBehavior_(
            _CAN_JOIN_ALL_SPACES | _STATIONARY | _FULLSCREEN_AUXILIARY)
    except Exception:
        _log.warning("原生置顶设置失败,回退 Qt 置顶", exc_info=True)
```

- [ ] **Step 4: 改写 overlay.py 渲染**

1. import 区:补 `import math`、`from PySide6.QtGui import QPainterPath, QPainterPathStroker`(并入现有 QtGui import),以及 `from sigtouch.interaction.features import INDEX_TIP`、`from sigtouch.ui.native import pin_window_topmost`。
2. 模块级新增两个纯函数:

```python
def align_to_cursor(points, index_tip_idx, cursor_px):
    """整体平移点集,使 points[index_tip_idx] 与 cursor_px 重合(光标钉在食指尖)。"""
    dx = cursor_px[0] - points[index_tip_idx][0]
    dy = cursor_px[1] - points[index_tip_idx][1]
    return [(x + dx, y + dy) for x, y in points]


def silhouette_path(points, palm_size_px):
    """把 21 个像素点合成实心手形(影子剪影):五指链粗圆描边 ∪ 掌心多边形。"""
    stroker = QPainterPathStroker()
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    finger_w = max(4.0, palm_size_px * 0.28)
    palm_w = max(8.0, palm_size_px * 0.55)
    path = QPainterPath()
    for chain in _FINGER_CHAINS:
        line = QPainterPath()
        line.moveTo(QPointF(*points[chain[0]]))
        for idx in chain[1:]:
            line.lineTo(QPointF(*points[idx]))
        stroker.setWidth(palm_w if chain == [0, 17] else finger_w)
        path = path.united(stroker.createStroke(line))
    palm = QPainterPath()
    palm.addPolygon(QPolygonF([QPointF(*points[i]) for i in _PALM_LOOP]))
    palm.closeSubpath()
    return path.united(palm)
```

3. `update_hand` 签名改为 `update_hand(self, hand, scale, feedback, cursor_px=None)`,新增 `self._cursor_px = cursor_px` 存储(`clear()` 中置 None;`__init__` 初始化为 None)。
4. `apply_screen()` 在 `self.show()` 之后追加 `pin_window_topmost(self)`。
5. `paintEvent` 中间段替换(两遍描边 + 掌心填充整体删除),改为:

```python
        pts = scaled_points(self._hand.landmarks, self.width(), self.height(),
                            self._scale)
        if self._cursor_px is not None:
            pts = align_to_cursor(pts, INDEX_TIP, self._cursor_px)
        palm_px = math.dist(pts[0], pts[9])
        color = QColor(self._cfg.get("display/overlay_color"))
        color.setAlphaF(min(1.0, self._cfg.get("display/overlay_opacity")))
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(silhouette_path(pts, palm_px), color)
```

6. 反馈图标改为高对比双层文本(深色影子上可读):

```python
        if self._feedback:
            wrist = pts[0]
            p.setFont(QFont("", int(28 * self._scale)))
            p.setPen(QColor(0, 0, 0, 230))
            p.drawText(QPointF(wrist[0] + 41, wrist[1] - 39), self._feedback)
            p.setPen(QColor(255, 255, 255, 240))
            p.drawText(QPointF(wrist[0] + 40, wrist[1] - 40), self._feedback)
```

7. `config.py`:`"display/overlay_color": "#FFFFFF"` 改为 `"#000000"`(注释:深色影子默认)。

- [ ] **Step 5: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 80 + 2 = 82

```bash
git add sigtouch/ui/native.py sigtouch/ui/overlay.py sigtouch/config.py \
        pyproject.toml tests/test_overlay_geometry.py
git commit -m "feat: dark hand-shadow silhouette, cursor alignment and native topmost"
```

---

### Task 5: app 接线(光标传参 + raise 兜底)

**Files:**
- Modify: `sigtouch/app.py`
- Test: `tests/test_app_permissions.py`(追加)

**Interfaces:**
- Consumes: `update_hand(..., cursor_px=)`(Task 4)。
- Produces: `_on_result` 把 mapper 输出同时用于注入与 overlay 对齐;watchdog tick 对可见 overlay 执行 `raise_()`。

- [ ] **Step 1: 写失败测试(追加到 tests/test_app_permissions.py)**

```python
def test_overlay_receives_mapper_cursor(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            self.moves = []

        def move(self, x, y):
            self.moves.append((x, y))

        def dispatch(self, ev):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    a = _make_app(monkeypatch)
    calls = []
    monkeypatch.setattr(
        a._overlay, "update_hand",
        lambda hand, scale, feedback, cursor_px=None: calls.append(cursor_px))
    a._on_result(FrameResult(timestamp_ms=0, hand=open_hand(),
                             face_distance_m=0.6, face_present=True))
    assert calls and calls[0] is not None
    ox, oy = a._screen_origin
    assert a._injector.moves[0] == (calls[0][0] + ox, calls[0][1] + oy)
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_app_permissions.py -v`
Expected: 新测试 FAIL(`cursor_px` 为 None / moves 不匹配)

- [ ] **Step 2: 修改 app.py**

`_on_result` 活动分支的 hand 段替换为:

```python
        if result.hand is not None:
            x, y = self._mapper.update(F.anchor_point(result.hand),
                                       self._machine.pinching,
                                       result.timestamp_ms)
            if self._injector is not None:
                self._injector.move(x + self._screen_origin[0],
                                    y + self._screen_origin[1])
            dist = result.face_distance_m if result.face_distance_m else 0.6
            scale = overlay_scale(dist,
                                  self._cfg.get("display/screen_diag_inch"))
            self._overlay.update_hand(result.hand, scale,
                                      self._machine.feedback, cursor_px=(x, y))
        else:
            self._overlay.clear()
```

`_check_watchdog` 中 `set_preview` 同步行之后追加:

```python
        if self._overlay.isVisible():
            self._overlay.raise_()  # 兜底:防止被后开窗口压住(macOS 另有原生层级)
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 82 + 1 = 83

```bash
git add sigtouch/app.py tests/test_app_permissions.py
git commit -m "feat: shadow follows mapper cursor and periodic overlay raise"
```

---

### Task 6: macOS .app 打包与文档

**Files:**
- Modify: `packaging/sigtouch.spec`, `.github/workflows/release.yml`, `README.md`, `packaging/README.md`, `docs/manual-qa.md`

**Interfaces:**
- Produces: `dist/SigTouch.app`(BUNDLE);release 资产 macOS 改为压缩 `.app`;manual-qa 第 12 项。

- [ ] **Step 1: spec 追加 BUNDLE**

`packaging/sigtouch.spec` 末尾(`coll = COLLECT(...)` 之后)追加:

```python
app = BUNDLE(
    coll,
    name="SigTouch.app",
    bundle_identifier="cn.sigtec.sigtouch",
    info_plist={
        "NSCameraUsageDescription":
            "SigTouch 需要摄像头识别手势以控制鼠标和键盘。",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    },
)
```

- [ ] **Step 2: 本地构建验证**

Run: `.venv/bin/pyinstaller packaging/sigtouch.spec`
Expected: 构建成功;`ls dist/` 同时含 `SigTouch/`(onedir)与 `SigTouch.app`;`plutil -lint dist/SigTouch.app/Contents/Info.plist` 输出 OK;`grep -c NSCameraUsageDescription dist/SigTouch.app/Contents/Info.plist` ≥1。

- [ ] **Step 3: release.yml macOS 打包改为 .app**

macOS Package 步骤替换为:

```yaml
      - name: Package (macOS)
        if: runner.os == 'macOS'
        run: cd dist && zip -qry ../SigTouch-${{ github.ref_name }}-macos-arm64.zip SigTouch.app
```

(BUNDLE 仅在 darwin 生效,Windows/Linux 构建不受影响。)

- [ ] **Step 4: 文档更新**

1. `README.md` macOS 小节替换为:

```markdown
- **macOS**:解压 `SigTouch-*-macos-arm64.zip` 得到 `SigTouch.app`;产物未签名,
  首次运行前解除隔离:`xattr -cr SigTouch.app`,然后双击(或 `open SigTouch.app`)启动。
  启动后按权限引导窗逐项授权摄像头、辅助功能、输入监控(授权后自动激活,无需重启);
  系统权限面板中显示的应用名即为 SigTouch。
```

2. `packaging/README.md` macOS 项替换为:

```markdown
- **macOS**:产出 `dist/SigTouch.app`(BUNDLE,含 NSCameraUsageDescription 等
  Info.plist 权限描述;同目录 `dist/SigTouch/` onedir 为中间产物);分发压缩
  `SigTouch.app`;`codesign` + 公证仍为后续工作,用户侧用 `xattr -cr` 解除隔离。
```

3. `docs/manual-qa.md` 追加:

```markdown
12. (v1.2)打包 .app 走查:`xattr -cr` 后双击 `SigTouch.app` 正常启动(权限面板显示
    SigTouch);全屏播放视频时手部影子仍显示在最上层;影子为深色实心剪影(非骨架),
    光标始终钉在影子食指尖上,捏合冻结期影子随光标停住;设置切换"控制手"为左手后,
    仅左手可控、右手被忽略(调试预览 hand= 标签核对),切回右手同理。
```

- [ ] **Step 5: 回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q` → 83
Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"`

```bash
git add packaging/sigtouch.spec .github/workflows/release.yml README.md \
        packaging/README.md docs/manual-qa.md
git commit -m "feat: bundle macOS .app with camera usage description"
```

---

## 最终验收清单

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` 全部通过(预期 83)。
2. 分支推送后 CI 三平台全绿。
3. 本地 `dist/SigTouch.app` 构建成功且 Info.plist 校验通过(Task 6 Step 2)。
4. 人工 QA(macOS 真机):`docs/manual-qa.md` 第 12 项走查通过。
5. 纯度 grep 与 PyQt grep 依旧为空。

## 后续工作(不在本计划)

- macOS 签名/公证;LSUIElement 托盘化隐藏 Dock 选项。
- Windows/Linux 原生层级增强(如遇具体压层问题)。
- 影子柔化边缘。

