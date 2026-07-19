# SigTouch v1.4 实现计划:多人场景与大屏缩放模型

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 多人时以最近者为操作者(主脸=瞳距最大、操作手=掌尺寸最大);缩放模型加入摄像头到屏距离与手影倍率两个设置,上限提至 5.0。

**Architecture:** 纯函数层扩展(`overlay_scale` 签名扩展、`select_primary_face` 新增、`select_hand` 升级)→ pipeline 接线(num_faces=3/num_hands=4/计数字段)→ 设置两项 + app 消费。三个任务依次纯函数→感知→UI/装配。

**Spec:** `docs/superpowers/specs/2026-07-19-multiperson-and-scale-design.md`

## Global Constraints

- 纯度约束不变(interaction/types/distance 不得 import cv2/mediapipe/PySide6/pynput)。
- `overlay_scale` 两参调用向后兼容(offset=0, multiplier=1);`select_hand` 签名不变;`FrameResult` 新字段带默认值 0(既有构造点零改动)。
- 新设置两键为**轻量键**(不得加入 `_RESTART_KEYS`)。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`(基线 95);提交前缀规范同前,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 文件结构总览

```
sigtouch/perception/distance.py    # overlay_scale 扩展 + SCALE_MAX 5.0(Task 1)
sigtouch/config.py                 # 两个新键(Task 1)
tests/test_distance.py             # 公式测试(Task 1)
sigtouch/perception/types.py       # FrameResult 计数字段(Task 2)
sigtouch/perception/pipeline.py    # select_primary_face + select_hand 升级 + 计数(Task 2)
sigtouch/ui/preview.py             # faces=N hands=M 叠加(Task 2)
tests/test_select_primary_face.py  # 新增(Task 2)
tests/test_select_hand.py          # 升级断言(Task 2)
sigtouch/ui/settings_dialog.py     # 显示页两项(Task 3)
sigtouch/app.py                    # overlay_scale 传参(Task 3)
tests/test_settings_instant.py tests/test_app_permissions.py docs/manual-qa.md  # (Task 3)
```

---

### Task 1: 缩放模型升级与配置键

**Files:**
- Modify: `sigtouch/perception/distance.py`, `sigtouch/config.py`, `tests/test_distance.py`

**Interfaces:**
- Produces: `overlay_scale(distance_m, diag_inch, offset_m=0.0, multiplier=1.0) -> float`(clamp 0.5~**5.0**;`d_screen = max(0.05, distance_m + offset_m)`);`DEFAULTS["display/camera_screen_offset_m"]=0.0`、`DEFAULTS["display/hand_scale_multiplier"]=1.0`。Task 3 消费。

- [ ] **Step 1: 更新/新增测试(先失败)**

`tests/test_distance.py`:`test_overlay_scale_formula_and_clamp` 中 `assert overlay_scale(5.0, 24.0) == pytest.approx(3.0)` 改为 `pytest.approx(5.0)`(上限提升;5.0/0.6×1=8.33 截到 5.0)。文件末尾追加:

```python
def test_overlay_scale_offset_shifts_screen_distance():
    # 摄像头在屏前 0.6m:人到屏 = 0.6+0.6 = 1.2m → 2.0
    assert overlay_scale(0.6, 24.0, offset_m=0.6) == pytest.approx(2.0)
    # 负偏移(摄像头在屏后,如屏前投影场景):1.2-0.6 = 0.6m → 1.0
    assert overlay_scale(1.2, 24.0, offset_m=-0.6) == pytest.approx(1.0)


def test_overlay_scale_multiplier():
    assert overlay_scale(0.6, 24.0, 0.0, 2.0) == pytest.approx(2.0)
    assert overlay_scale(3.0, 24.0, 0.0, 2.0) == pytest.approx(5.0)  # 10.0 截到上限


def test_overlay_scale_floor_protection_on_extreme_negative_offset():
    # d_screen 被压到 0.05m 下限 → raw 极小 → 下限 0.5
    assert overlay_scale(0.3, 24.0, offset_m=-0.5) == pytest.approx(0.5)


def test_overlay_scale_two_arg_backward_compat():
    assert overlay_scale(1.2, 24.0) == pytest.approx(2.0)
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_distance.py -v`
Expected: 新测试 FAIL(TypeError/上限断言失败)

- [ ] **Step 2: 实现**

`config.py` display 段追加:

```python
    "display/camera_screen_offset_m": 0.0,  # 摄像头到屏幕平面距离(米,摄像头在屏前为正)
    "display/hand_scale_multiplier": 1.0,   # 手影大小倍率(物理模型后的用户微调)
```

`distance.py`:`SCALE_MIN, SCALE_MAX = 0.5, 3.0` 改为 `0.5, 5.0`;新增常量 `_MIN_SCREEN_DISTANCE_M = 0.05`;`overlay_scale` 替换为:

```python
def overlay_scale(distance_m: float, diag_inch: float,
                  offset_m: float = 0.0, multiplier: float = 1.0) -> float:
    """轮廓大小(占屏比例)相对基准的倍率:比例 ∝ 人到屏距离 ÷ 屏幕尺寸,再乘用户倍率。

    distance_m 是虹膜法测得的人到摄像头距离;offset_m 是摄像头到屏幕平面的距离
    (摄像头在屏幕前为正),两者之和才是缩放所需的人到屏幕距离。
    """
    d_screen = max(_MIN_SCREEN_DISTANCE_M, distance_m + offset_m)
    raw = (d_screen / REF_DISTANCE_M) * (REF_DIAG_INCH / diag_inch) * multiplier
    return max(SCALE_MIN, min(SCALE_MAX, raw))
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 95 + 4 = 99

```bash
git add sigtouch/perception/distance.py sigtouch/config.py tests/test_distance.py
git commit -m "feat: camera-to-screen offset and hand-scale multiplier in overlay scale"
```

---

### Task 2: 多人选择与计数

**Files:**
- Modify: `sigtouch/perception/types.py`, `sigtouch/perception/pipeline.py`, `sigtouch/ui/preview.py`, `tests/test_select_hand.py`
- Test: `tests/test_select_primary_face.py`(新增)

**Interfaces:**
- Produces: `FrameResult` 新字段 `face_count: int = 0`、`hand_count: int = 0`;`pipeline.select_primary_face(faces) -> face | None`(瞳距像素最大);`select_hand(hands, wanted)` 升级为过滤后取掌尺寸最大(签名不变);`num_faces=3`、`num_hands=4`。

- [ ] **Step 1: 更新/新增测试(先失败)**

`tests/test_select_hand.py`:`test_duplicate_labels_take_first` 整体替换为:

```python
def test_duplicate_labels_take_largest_palm():
    def hand(palm_size):
        lms = [(0.5, 0.5, 0.0)] * 21
        lms[9] = (0.5, 0.5 - palm_size, 0.0)  # 腕(0)到中指根(9)的距离即掌尺寸
        return lms

    small, big = hand(0.08), hand(0.15)
    assert select_hand([("Right", small), ("Right", big)], "Right") is big
    assert select_hand([("Right", big), ("Right", small)], "Right") is big  # 与顺序无关
```

新增 `tests/test_select_primary_face.py`:

```python
from types import SimpleNamespace

from sigtouch.perception.pipeline import select_primary_face


def _face(span):
    """构造只有虹膜两点有意义的假脸:468/473 水平相距 span(归一化)。"""
    pts = [None] * 478
    pts[468] = SimpleNamespace(x=0.5 - span / 2, y=0.5)
    pts[473] = SimpleNamespace(x=0.5 + span / 2, y=0.5)
    return pts


def test_empty_returns_none():
    assert select_primary_face([]) is None


def test_single_face_selected():
    f = _face(0.05)
    assert select_primary_face([f]) is f


def test_larger_iris_span_wins():
    far, near = _face(0.03), _face(0.09)
    assert select_primary_face([far, near]) is near
    assert select_primary_face([near, far]) is near


def test_tie_takes_first():
    a, b = _face(0.05), _face(0.05)
    assert select_primary_face([a, b]) is a
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_select_primary_face.py tests/test_select_hand.py -v`
Expected: FAIL(`ImportError: select_primary_face`;掌尺寸测试失败)

- [ ] **Step 2: 实现**

`types.py` FrameResult 追加两字段(注释:多人调试计数):

```python
    face_count: int = 0            # 本帧检出人脸数(多人调试)
    hand_count: int = 0            # 本帧检出手数(多人调试)
```

`pipeline.py`:
1. `num_hands=2` → `num_hands=4`;`num_faces=1` → `num_faces=3`。
2. `select_hand` 替换为:

```python
def select_hand(hands, wanted):
    """按 handedness 过滤后取手掌尺寸最大者(最近的人的手);无匹配返回 None。

    掌尺寸 = 腕(0)到中指根(9)的归一化距离,与 features.palm_size 同定义。
    """
    best = None
    best_size = -1.0
    for label, lms in hands:
        if label != wanted:
            continue
        size = math.dist(lms[0][:2], lms[9][:2])
        if size > best_size:
            best, best_size = lms, size
    return best
```

3. 模块级新增:

```python
def select_primary_face(faces):
    """取瞳距像素最大(离摄像头最近)的脸;空列表返回 None。"""
    best = None
    best_span = -1.0
    for f in faces:
        r, l = f[_RIGHT_IRIS_CENTER], f[_LEFT_IRIS_CENTER]
        span = math.hypot(r.x - l.x, r.y - l.y)
        if span > best_span:
            best, best_span = f, span
    return best
```

4. `process()`:人脸段把 `f = fres.face_landmarks[0]` 改为 `f = select_primary_face(fres.face_landmarks)`(非空分支内,f 不可能为 None);返回值构造追加 `face_count=len(fres.face_landmarks or [])`、`hand_count=len(hres.hand_landmarks or [])`。

`preview.py` `update_frame` 中 `dist=` 行之后追加(在 `r is not None` 分支内、hand 分支外):

```python
        if r is not None:
            cv2.putText(bgr, f"faces={r.face_count} hands={r.hand_count}",
                        (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (200, 200, 200), 2)
```

(按 preview 现有结构接入:该文件已有 `if r is not None` 判断,合并进去,不重复判断。)

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 99 + 5 = 104(黑帧冒烟测试照常:无手无脸,计数 0)

```bash
git add sigtouch/perception/types.py sigtouch/perception/pipeline.py \
        sigtouch/ui/preview.py tests/test_select_hand.py tests/test_select_primary_face.py
git commit -m "feat: nearest-person operator selection and detection counts"
```

---

### Task 3: 设置两项与 app 消费

**Files:**
- Modify: `sigtouch/ui/settings_dialog.py`, `sigtouch/app.py`, `docs/manual-qa.md`
- Test: `tests/test_settings_instant.py`, `tests/test_app_permissions.py`(各追加)

**Interfaces:**
- 显示页新增「摄像头到屏幕距离(米)」dspin(-2.0~10.0, step 0.1, 1 位小数)与「手影大小倍率」滑杆(50–300% ↔ /100);两键不入 `_RESTART_KEYS`。
- `app._on_result` 的 `overlay_scale(...)` 调用追加 offset 与 multiplier 两参。

- [ ] **Step 1: 写失败测试**

`tests/test_settings_instant.py` 追加:

```python
def test_scale_keys_are_light_and_instant(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("display/camera_screen_offset_m").setValue(1.5)
    assert dlg._cfg.get("display/camera_screen_offset_m") == pytest.approx(1.5)
    dlg.field_widget("display/hand_scale_multiplier").setValue(200)
    assert dlg._cfg.get("display/hand_scale_multiplier") == pytest.approx(2.0)
    assert dlg._apply_timer.isActive() is True     # 轻量合并
    assert dlg._restart_timer.isActive() is False  # 不触发视觉重启
```

`tests/test_app_permissions.py` 追加:

```python
def test_overlay_scale_consumes_offset_and_multiplier(qapp, monkeypatch):
    state = {k: True for k in K}
    _patch_perms(monkeypatch, state)

    class FakeInjector:
        def __init__(self):
            pass

        def move(self, x, y):
            pass

        def dispatch(self, ev):
            pass

        def release_all(self):
            pass

    monkeypatch.setattr(app_module, "Injector", FakeInjector)
    monkeypatch.setattr(SigTouchApp, "_setup_hotkey", lambda self: None)
    monkeypatch.setattr(
        SigTouchApp, "_start_vision",
        lambda self: setattr(self, "_vision", _VisionStub()))
    from sigtouch.config import Config as _Config
    cfg = _Config(backend={"display/hand_scale_multiplier": 2.0})
    a = SigTouchApp(cfg)
    scales = []
    monkeypatch.setattr(
        a._overlay, "update_hand",
        lambda hand, scale, feedback, cursor_px=None: scales.append(scale))
    a._on_result(FrameResult(timestamp_ms=0, hand=open_hand(),
                             face_distance_m=0.6, face_present=True))
    assert scales and scales[0] == pytest.approx(2.0)  # 0.6m/24吋 基准 1.0 × 倍率 2.0
```

(该文件顶部如无 `import pytest` 则补;`FrameResult`/`open_hand`/`K`/`_patch_perms`/`_VisionStub`/`app_module`/`SigTouchApp` 均已存在。)

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_instant.py tests/test_app_permissions.py -v`
Expected: FAIL(`KeyError: display/camera_screen_offset_m`;scale 断言 1.0≠2.0)

- [ ] **Step 2: 实现**

`settings_dialog.py` `_display_page` 中「目标显示器」行之前插入:

```python
        self._row(form, "摄像头到屏幕距离(米)",
                  self._dspin("display/camera_screen_offset_m", -2.0, 10.0, 0.1, 1),
                  "摄像头装在屏幕前方时填正值;0 表示摄像头就在屏幕平面(如笔记本)")
        self._row(form, "手影大小倍率",
                  self._slider("display/hand_scale_multiplier", 50, 300,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"),
                  "物理模型算完后的整体微调,大屏看不清就调大")
```

`app.py` `_on_result` 中 `scale = overlay_scale(dist, self._cfg.get("display/screen_diag_inch"))` 替换为:

```python
            scale = overlay_scale(
                dist, self._cfg.get("display/screen_diag_inch"),
                self._cfg.get("display/camera_screen_offset_m"),
                self._cfg.get("display/hand_scale_multiplier"))
```

`docs/manual-qa.md` 追加:

```markdown
14. (v1.4)多人与大屏走查:两人入镜,后排旁观者同侧手不夺控、其走近至最前排后接管
    (预览窗 faces/hands 计数与主控切换核对);大屏标定:量出摄像头到屏幕平面距离填入
    设置,影子大小随之变化;手影大小倍率拖动实时生效;极端负偏移不导致影子消失
    (有 0.5 下限保护)。
```

- [ ] **Step 3: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 104 + 2 = 106

```bash
git add sigtouch/ui/settings_dialog.py sigtouch/app.py docs/manual-qa.md \
        tests/test_settings_instant.py tests/test_app_permissions.py
git commit -m "feat: camera-offset and hand-scale settings wired into overlay scale"
```

---

## 最终验收清单

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` 全部通过(预期 106)。
2. 分支推送后 CI 三平台全绿。
3. 人工 QA:`docs/manual-qa.md` 第 14 项(需两人 + 真机)。
4. 纯度 grep 与 PyQt grep 为空。

## 后续工作(不在本计划)

- 跨帧人员锁定;手脸关联;摄像头距离自动标定。
