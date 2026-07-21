# SigTouch v1.7 实现计划:手影尺寸钳制与出界修复

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 手影高度钳制到屏幕高度的可配置比例(默认 25%)并尽量落入屏幕,收缩围绕食指尖以保持「光标始终在食指上」契约。

**Architecture:** 新增纯函数 `fit_hand_to_screen`(overlay 模块内,几何计算无 Qt 依赖)→ 接入 paintEvent 渲染链尾部 → 新增配置键与设置滑杆。

**Spec:** `docs/superpowers/specs/2026-07-20-hand-size-fit-design.md`

## Global Constraints

- **anchor 不变量**:`fit_hand_to_screen` 返回的点集中,`anchor_idx` 处的点必须与输入**完全相同**(浮点精确相等)——这是 v1.2「光标钉食指」契约的基础。
- 收缩系数下限 `min_shrink=0.5`,防止光标贴角时手影塌缩不可见。
- 新配置键为轻量键,不得加入 `_RESTART_KEYS`。
- `overlay_scale` 与 `align_to_cursor` 不改动。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`(基线 140);提交前缀规范同前,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 文件结构总览

```
sigtouch/ui/overlay.py            # fit_hand_to_screen + paintEvent 接入(Task 1)
sigtouch/config.py                # hand_max_screen_fraction(Task 1)
tests/test_hand_fit.py            # 新增(Task 1)
sigtouch/ui/settings_dialog.py    # 手影最大高度滑杆(Task 2)
tests/test_settings_instant.py    # 追加(Task 2)
docs/manual-qa.md                 # 第 17 项(Task 2)
```

---

### Task 1: fit_hand_to_screen 与渲染接入

**Files:**
- Modify: `sigtouch/ui/overlay.py`, `sigtouch/config.py`
- Test: `tests/test_hand_fit.py`

**Interfaces:**
- Produces: `fit_hand_to_screen(points, anchor_idx, screen_w, screen_h, max_h_fraction, min_shrink=0.5) -> list[tuple[float,float]]`;`DEFAULTS["display/hand_max_screen_fraction"] = 0.25`。Task 2 的设置控件绑定同一键。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_hand_fit.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from sigtouch.ui.overlay import fit_hand_to_screen

W, H = 1920, 1080
ANCHOR = 1  # 点 1 作为锚点(模拟食指尖)


def _tall_hand(anchor_xy=(960.0, 540.0), height=540.0):
    """锚点在顶端、主体向下延伸 height 的点集(模拟真实手形)。"""
    ax, ay = anchor_xy
    return [(ax - 100.0, ay), (ax, ay), (ax + 100.0, ay + height)]


def test_oversized_hand_shrinks_to_limit():
    pts = _tall_hand(height=540.0)          # 占屏高 50%
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    ys = [p[1] for p in out]
    assert (max(ys) - min(ys)) == pytest.approx(H * 0.25)


def test_anchor_never_moves():
    pts = _tall_hand(anchor_xy=(300.0, 200.0), height=800.0)
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    assert out[ANCHOR] == pts[ANCHOR]       # 浮点精确相等:光标对齐不被破坏


def test_within_limit_returns_unchanged():
    pts = _tall_hand(height=200.0)          # 已在 25% 限制内
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    assert out == pts


def test_bottom_edge_shrinks_into_screen():
    pts = _tall_hand(anchor_xy=(960.0, 1000.0), height=270.0)  # 会向下出界
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25)
    assert max(p[1] for p in out) <= H + 1e-6                  # 收进屏幕


def test_min_shrink_floor_keeps_hand_visible():
    # 锚点贴最底边:任何收缩都无法完全收进 → 触及下限 0.5,但仍可见
    pts = _tall_hand(anchor_xy=(960.0, 1079.0), height=540.0)
    out = fit_hand_to_screen(pts, ANCHOR, W, H, 0.25, min_shrink=0.5)
    span = max(p[1] for p in out) - min(p[1] for p in out)
    assert span > 0                                    # 未塌缩
    assert span >= (H * 0.25) * 0.5 - 1e-6             # 不低于 尺寸限制×下限


def test_degenerate_inputs_do_not_raise():
    flat = [(10.0, 50.0), (20.0, 50.0), (30.0, 50.0)]  # 零高度
    assert fit_hand_to_screen(flat, ANCHOR, W, H, 0.25) == flat
    single = [(5.0, 5.0)]
    assert fit_hand_to_screen(single, 0, W, H, 0.25) == single
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_hand_fit.py -v`
Expected: FAIL(`ImportError: fit_hand_to_screen`)

- [ ] **Step 2: 实现 fit_hand_to_screen**

`sigtouch/ui/overlay.py` 在 `align_to_cursor` 之后新增:

```python
def fit_hand_to_screen(points, anchor_idx, screen_w, screen_h,
                       max_h_fraction, min_shrink=0.5):
    """围绕 anchor(食指尖)收缩手影:限制高度占屏比例,并尽量收进屏幕。

    anchor 点位置恒不变——光标始终钉在食指上(v1.2 契约)。
    收缩系数不低于 min_shrink,避免光标贴角时手影塌缩为不可见。
    """
    if len(points) < 2:
        return points
    ax, ay = points[anchor_idx]
    ys = [p[1] for p in points]
    bbox_h = max(ys) - min(ys)
    if bbox_h <= 0:
        return points

    # (a) 尺寸上限
    limit = screen_h * max_h_fraction
    k = limit / bbox_h if bbox_h > limit else 1.0

    # (b) 边缘收缩:令 anchor + k·offset 落在屏幕矩形内
    for x, y in points:
        dx, dy = x - ax, y - ay
        if dx > 0:
            k = min(k, (screen_w - ax) / dx)
        elif dx < 0:
            k = min(k, -ax / dx)
        if dy > 0:
            k = min(k, (screen_h - ay) / dy)
        elif dy < 0:
            k = min(k, -ay / dy)

    k = max(min_shrink, min(1.0, k))
    if k >= 1.0:
        return points
    return [(ax + (x - ax) * k, ay + (y - ay) * k) for x, y in points]
```

- [ ] **Step 3: 接入 paintEvent 并加配置键**

`config.py` display 段追加:

```python
    "display/hand_max_screen_fraction": 0.25,  # 手影高度上限(占屏幕高度比例)
```

`overlay.py` `paintEvent` 中,`align_to_cursor` 之后、`palm_px` 计算之前插入:

```python
        anchor_idx = INDEX_TIP if self._cursor_px is not None else 0
        pts = fit_hand_to_screen(
            pts, anchor_idx, self.width(), self.height(),
            self._cfg.get("display/hand_max_screen_fraction"))
```

(`cursor_px` 为 None 时以点 0 为锚做尺寸钳制,行为退化安全;`palm_px` 在其后计算,描边随之同步收缩。)

- [ ] **Step 4: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 140 + 6 = 146

```bash
git add sigtouch/ui/overlay.py sigtouch/config.py tests/test_hand_fit.py
git commit -m "fix: clamp hand shadow height and fit it inside the screen"
```

---

### Task 2: 设置滑杆与文档

**Files:**
- Modify: `sigtouch/ui/settings_dialog.py`, `docs/manual-qa.md`
- Test: `tests/test_settings_instant.py`(追加)

- [ ] **Step 1: 写失败测试(追加)**

```python
def test_hand_max_fraction_is_light_key(qapp):
    dlg = _dlg(qapp)
    dlg.field_widget("display/hand_max_screen_fraction").setValue(40)
    assert dlg._cfg.get("display/hand_max_screen_fraction") == pytest.approx(0.40)
    assert dlg._apply_timer.isActive() is True      # 轻量合并
    assert dlg._restart_timer.isActive() is False   # 不重启视觉线程
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_instant.py -v`
Expected: FAIL(`KeyError`)

- [ ] **Step 2: 显示页加滑杆**

`_display_page` 中「手影大小倍率」之后插入:

```python
        self._row(form, "手影最大高度",
                  self._slider("display/hand_max_screen_fraction", 10, 60,
                               lambda v: v / 100.0,
                               lambda s: round(float(s) * 100),
                               lambda v: f"{v}%"),
                  "手影高度上限,占屏幕高度的比例;超过时自动收缩并收进屏幕")
```

- [ ] **Step 3: manual-qa 第 17 项**

```markdown
17. (v1.7)手影尺寸走查:笔记本上手影高度约占屏幕高度 1/4(不再近半屏);光标移到
    屏幕四角与底边,手影完整可见或仅极端角落小幅裁剪,食指尖始终贴合光标不偏移;
    拖动设置-显示页「手影最大高度」滑杆,手影随之实时变大变小;前后走动时手影大小
    保持稳定(物理模型未被破坏)。
```

- [ ] **Step 4: 全量回归 + 提交**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` → 146 + 1 = 147

```bash
git add sigtouch/ui/settings_dialog.py docs/manual-qa.md tests/test_settings_instant.py
git commit -m "feat: hand max height setting and QA walkthrough"
```

---

## 最终验收清单

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v` 全部通过(预期 147)。
2. 分支推送后 CI 三平台全绿。
3. anchor 不变量在所有 fit 路径成立(测试保证)。
4. 人工 QA:`docs/manual-qa.md` 第 17 项。
5. 纯度 grep 与 PyQt grep 为空。

## 后续工作(不在本计划)

- 按画面中手的真实像素尺寸自适应(当前几何模型 + 钳制已足够)。
- 极端角落的手影塌缩策略微调(现为 min_shrink 下限)。
