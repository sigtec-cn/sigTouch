# SigTouch v1.9 实现计划:手势动画重做、拇指向左退格与 shadcn 界面

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 进度动画以光标为正中心、固定小尺寸、shadcn 质感;退格改拇指向左(替换推手);全部触发计时默认 1500ms 可调;主题换 zinc + lucide 图标全面去 emoji。

**Spec:** `docs/superpowers/specs/2026-07-22-gesture-anim-and-shadcn-design.md`

## Global Constraints

- 上游 4b9c1d0/6963bc7 的代码结构非本计划所写:实现者必须**先读目标文件**再动手;本计划的具名测试与契约是硬性规格,行级指令以现有结构为准适配。
- 硬契约:`GestureProgress` 结构与 `update_hand(hand, scale, progress, cursor_px=None)` 签名不变;`_apply_state`/`_ui_state` 单一入口不变;`fit_hand_to_screen` 锚点不变量不变;pin/unpin cocoa 门控勿删;`_setup_hotkey` 的 `_hotkey_needs_restart` 守卫勿删。
- 测试基线 170;每任务的**具名新测试必须全部存在并通过**;总数以实际为准(上游测试文件结构不做脆计数断言),实现者报告净变化。
- 测试命令 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`;提交前缀规范同前,结尾:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## 任务总览

```
Task 1  拇指向左退格 + 计时统一(features/gestures/config/settings 滑杆)
Task 2  进度动画重做(overlay:光标中心、固定尺寸、shadcn 质感、← 图标)
Task 3  zinc 主题 + lucide 图标模块
Task 4  全面去 emoji(导航/向导/托盘/状态徽章)+ manual-qa 18
```

---

### Task 1: 拇指向左退格与计时统一

**Files:**
- Modify: `sigtouch/interaction/features.py`, `sigtouch/interaction/gestures.py`, `sigtouch/config.py`, `sigtouch/ui/settings_dialog.py`, `tests/hand_fixtures.py`, 既有 gestures/push 相关测试
- Test: `tests/test_thumbs_left.py`(新增)

**硬契约:**
- `features.is_thumbs_left(hand) -> bool`:四指全弯曲(`not any(fingers_extended(hand))`)+ 拇指伸直(tip 腕距 > mcp 腕距 × 1.05,与 `is_thumbs_up` 同准)+ 指向用户视角左:`thumb_mcp.x - thumb_tip.x > palm_size(hand) * 0.6`。不依赖 handedness。
- gestures:PUSH 面积增长机制整体删除(`_push_start/_update_push` 及 `push_area_ratio/push_window_ms` 消费);新 `THUMBS_LEFT` 状态与 `THUMBS_UP` 同构(进入判定 `is_thumbs_left`、保持 `interaction/thumbs_left_hold_ms` 触发 BACKSPACE、提前松开不触发、`GestureProgress(kind="backspace")`、cooldown 与 `gestures/backspace` 开关照旧);判定顺序 thumbs_up 优先于 thumbs_left(两者姿态互斥,顺序仅作决断)。
- config:`interaction/thumbs_left_hold_ms: 1500` 新增;`interaction/thumbs_up_hold_ms` 默认 800→**1500**;`interaction/push_hold_ms`、`interaction/push_area_ratio`、`interaction/push_window_ms` 从 DEFAULTS 删除。
- settings 「手势判定时间」组:三滑杆 = 捏合(`pinch_hold_ms`)/竖拇指(`thumbs_up_hold_ms`)/拇指向左(`thumbs_left_hold_ms`),范围统一 **500–3000ms**,说明文字相应更新;推手滑杆删除。

**Steps:**

- [ ] **Step 1**:`tests/hand_fixtures.py` 新增 `thumbs_left(**kw)` 夹具(参考现有 `thumbs_up` 的构造方式:四指弯曲,拇指 tip 置于 mcp 左侧 `palm×0.8` 处、y 同高);写失败测试:

```python
# tests/test_thumbs_left.py
import pytest

from sigtouch.config import Config
from sigtouch.interaction import features as F
from sigtouch.interaction.gestures import EventKind, GestureStateMachine
from tests.hand_fixtures import open_hand, thumbs_left, thumbs_up


def _machine():
    return GestureStateMachine(Config(backend={}))


def _run(m, frames):
    out = []
    for hand, t in frames:
        out.extend(m.update(hand, t))
    return out


def test_is_thumbs_left_detects_left_pointing_thumb():
    assert F.is_thumbs_left(thumbs_left()) is True
    assert F.is_thumbs_left(open_hand()) is False
    assert F.is_thumbs_left(thumbs_up()) is False          # 与竖拇指互斥


def test_is_thumbs_left_hand_agnostic():
    assert F.is_thumbs_left(thumbs_left(handedness="Left")) is True


def test_thumbs_up_not_confused_with_left():
    assert F.is_thumbs_up(thumbs_left()) is False


def test_hold_1500ms_fires_backspace_once():
    m = _machine()
    frames = [(open_hand(), 0)] + \
             [(thumbs_left(), 33 * i) for i in range(1, 70)]  # 持续到 ~2.3s
    evs = _run(m, frames)
    assert [e.kind for e in evs] == [EventKind.BACKSPACE]


def test_early_release_no_backspace():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (thumbs_left(), 33),
                   (thumbs_left(), 800), (open_hand(), 900)])  # 不足 1500ms
    assert evs == []


def test_backspace_progress_reported():
    m = _machine()
    m.update(open_hand(), 0)
    m.update(thumbs_left(), 33)
    m.update(thumbs_left(), 780)     # ~50%
    p = m.progress
    assert p is not None and p.kind == "backspace"
    assert 0.3 < p.fraction < 0.7


def test_push_keys_removed_from_defaults():
    cfg = Config(backend={})
    for key in ("interaction/push_hold_ms", "interaction/push_area_ratio",
                "interaction/push_window_ms"):
        with pytest.raises(KeyError):
            cfg.get(key)
    assert cfg.get("interaction/thumbs_left_hold_ms") == 1500
    assert cfg.get("interaction/thumbs_up_hold_ms") == 1500
```

- [ ] **Step 2**:实现(先读 gestures.py 现有 THUMBS_UP 分支照式复制);删除/改写既有推手测试(`tests/test_gestures_symbolic.py` 等中 push 相关用例改为 thumbs_left 语义或删除,**不得为凑通过而弱化断言**);`tests/test_gesture_progress.py` 中 backspace 进度用例改用 thumbs_left 驱动;settings 滑杆组替换 + 既有 settings 测试适配;thumbs_up 相关既有测试的 800ms 时序驱动序列按 1500 调整。
- [ ] **Step 3**:全量回归(具名测试全过,总数报告净变化)→ 提交 `feat: thumbs-left backspace and unified 1500ms hold defaults`。

---

### Task 2: 进度动画重做

**Files:**
- Modify: `sigtouch/ui/overlay.py`,相关既有动画测试
- Test: `tests/test_progress_geometry.py`(新增)

**硬契约:**
- 新模块级纯函数 `progress_geometry(cursor_px) -> tuple[tuple[float, float], float]`:返回 `(center, radius)`,`center == cursor_px`(正中心),`radius == _RING_RADIUS`(模块常量 22.0);`cursor_px is None` 时返回 `(None, 0.0)`,绘制层据此**跳过**进度绘制。
- 常量:`_RING_RADIUS = 22.0`、`_RING_STROKE = 3.0`、`_GLYPH_SIZE = 18.0`——逻辑像素,**不乘 scale/palm_px**。
- 视觉:轨道整圆 zinc `rgba(24,24,27,64)` 3px;进度弧白 `rgba(255,255,255,242)` 3px 圆头端帽,12 点起顺时针;图标(enter ↵ 描画保留、backspace 改**单一 ← 左箭头**笔画)环内 2px 白线按 fraction 描画;右键标识 = 环旁 4 点方向 3px 白点;触发闪烁改为环 22→30 扩散 + alpha 衰减 160ms。
- `update_hand` 签名与 `GestureProgress` 消费不变;旧的 palm_px 偏移/缩放锚点逻辑删除。

**Steps:**

- [ ] **Step 1**:失败测试:

```python
# tests/test_progress_geometry.py
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from sigtouch.ui.overlay import (_GLYPH_SIZE, _RING_RADIUS, _RING_STROKE,
                                 progress_geometry)


def test_centered_exactly_on_cursor():
    center, radius = progress_geometry((960.0, 540.0))
    assert center == (960.0, 540.0)
    assert radius == _RING_RADIUS


def test_constants_are_fixed_logical_px():
    assert _RING_RADIUS == 22.0
    assert _RING_STROKE == 3.0
    assert _GLYPH_SIZE == 18.0


def test_no_cursor_no_geometry():
    center, radius = progress_geometry(None)
    assert center is None and radius == 0.0
```

- [ ] **Step 2**:实现(先读 `_paint_progress/_paint_ring/_draw_strokes_partial` 现状);`_BACKSPACE_STROKES` 改为单一 ← 箭头(单位坐标折线:横线 (0.8,0)→(-0.8,0) + 两斜笔 (-0.8,0)→(-0.2,-0.5)、(-0.8,0)→(-0.2,0.5));删除旧锚点偏移与 palm 缩放;既有动画测试(如有断言旧锚点/尺寸者)按新契约改写。
- [ ] **Step 3**:离屏冒烟:构造 overlay,喂 hand+progress+cursor,`grab()` 渲染无异常;全量回归 → 提交 `feat: cursor-centered fixed-size progress ring with refined visuals`。

---

### Task 3: zinc 主题与 lucide 图标模块

**Files:**
- Modify: `sigtouch/ui/theme.py`, `tests/test_theme.py`
- Create: `sigtouch/ui/lucide.py`
- Test: `tests/test_lucide.py`(新增)

**硬契约:**
- theme token 新值(spec §4.1 表格照抄):BG `#FAFAFA`、CARD `#FFFFFF`、BORDER `#E4E4E7`、TEXT `#09090B`、TEXT_MUTED `#71717A`、ACCENT `#18181B`、ACCENT_HOVER `#27272A`;OK/WARN/DANGER 不变;QSS 结构不变(选择器名不动,仅色值随 token)。
- `lucide.icon(name: str, color: str = theme.TEXT, size: int = 16) -> QIcon`:QtSvg 渲染(2x 超采样防糊);未知名抛 `KeyError`;模块头注明 lucide ISC 许可与来源;内嵌图标(24×24 viewBox 原始 path,stroke 模式,stroke-width 2):`camera, hand, palette, settings, mouse-pointer, keyboard, check, x, triangle-alert, rotate-cw, video, shield, power, circle, pause, play`(circle 需支持 `fill` 参数变体:`icon("circle", color, size, fill=True)` 实心)。
- lucide SVG path 数据从官方图标集准确转写(实现者用已知的 lucide path 数据;渲染冒烟测试兜底正确性)。

**Steps:**

- [ ] **Step 1**:失败测试:

```python
# tests/test_lucide.py
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
    from sigtouch.ui.lucide import icon
    for name in NAMES:
        ic = icon(name)
        assert not ic.isNull(), name
        assert not ic.pixmap(16, 16).isNull(), name


def test_unknown_name_raises(qapp):
    from sigtouch.ui.lucide import icon
    with pytest.raises(KeyError):
        icon("no-such-icon")


def test_filled_circle_variant(qapp):
    from sigtouch.ui.lucide import icon
    assert not icon("circle", "#10B981", 12, fill=True).isNull()
```

`tests/test_theme.py` 的 token 断言按新值更新(若有 assert 具体色值)。

- [ ] **Step 2**:实现 lucide.py 与 theme 色值;`QT_QPA_PLATFORM=offscreen` 下构造 SettingsDialog 冒烟(主题应用后正常渲染)。
- [ ] **Step 3**:全量回归 → 提交 `feat: zinc shadcn theme and embedded lucide icon module`。

---

### Task 4: 全面去 emoji 与文档

**Files:**
- Modify: `sigtouch/ui/settings_dialog.py`, `sigtouch/ui/permission_wizard.py`, `sigtouch/ui/tray.py`, `docs/manual-qa.md`,相关既有测试断言
- Test: `tests/test_no_emoji.py`(新增)

**硬契约(替换表 = spec §4.3)**:
- 设置导航:`_NAV_ITEMS` 文字去前缀,`QListWidgetItem.setIcon(lucide.icon(...))`(camera/hand/palette/settings);
- 向导:行图标 QLabel(pixmap 20px:camera/mouse-pointer/keyboard);成功横幅 check 图标+纯文字;重启提示 triangle-alert 图标+纯文字、重启按钮 setIcon(rotate-cw);徽章改 图标(check/x, 12px, 白色)+纯文字「已授权/未授权」(badge 容器:QFrame 内 icon QLabel + text QLabel;保留 `_status_labels[kind]` 指向**文字 QLabel**,`badge-ok/badge-danger` class 移到容器);
- 托盘:各 QAction `setIcon`(settings/shield/video/pause/play/power),文字去 emoji 前缀(「设置…」「权限设置…」「调试预览」「暂停/恢复」「退出」);`_STATE_META` 第三元组去 emoji(「暂停」「恢复」);`set_state` 同步更新 toggle 图标 pause/play;
- 设置状态徽章 `_STATE_TEXT`:去 ● 前缀,`_status_badge` 改容器(circle 实心图标按语义色 + 文字),保留 `set_running_state(state)` 接口;
- 既有测试断言适配(**列全,不得遗漏**):wizard 徽章 `startswith("✓")` → `"已授权" in` / `startswith("✗")` → `"未授权" in`;tray toggle `"⏸ 暂停"` 等精确断言 → 纯文字 `"暂停"`/`"恢复"`(含 hotkey 后缀用例同步);设置状态条 `"使用中" in` 等已是子串不动;其他以 grep emoji 定位。

**Steps:**

- [ ] **Step 1**:失败守卫测试:

```python
# tests/test_no_emoji.py
from pathlib import Path

# UI 源码不得再含 emoji/装饰符号(lucide 图标全面替代)
_BANNED = ["📷", "✋", "🎨", "⚙️", "🖱️", "⌨️", "🔐", "🎥", "⏸", "▶", "⏻",
           "✓", "✗", "⚠️", "●", "👍"]
_UI_DIR = Path(__file__).resolve().parent.parent / "sigtouch" / "ui"


def test_ui_sources_contain_no_emoji():
    offenders = []
    for py in _UI_DIR.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for ch in _BANNED:
            if ch in text:
                offenders.append(f"{py.name}: {ch}")
    assert offenders == [], offenders
```

(注意 overlay.py 若有 ↵/← 等笔画注释不在禁列;`_BANNED` 若误伤合法内容,调整清单并在报告说明。)

- [ ] **Step 2**:按替换表实现;逐一适配既有断言;`docs/manual-qa.md` 追加:

```markdown
18. (v1.9)动画与界面走查:捏合/竖拇指/拇指向左时进度环以光标为正中心、约 44px 直径
    细描边、触发时柔和扩散闪烁,大屏与近距下尺寸不变;拇指向左(左右手皆指向屏幕左侧)
    保持 1.5 秒触发退格;三个手势计时滑杆默认均 1500ms;设置窗/权限向导/托盘菜单为
    shadcn 中性风格(黑色主按钮、细灰边框),所有图标为线性矢量图标,无任何 emoji。
```

- [ ] **Step 3**:全量回归(具名测试全过)→ 提交 `feat: lucide icons everywhere, no emoji, shadcn polish`。

---

## 最终验收清单

1. 全量测试通过(具名测试全部存在;总数以实际为准,报告净变化)。
2. 分支推送后 CI 三平台全绿。
3. `grep -rE "📷|✋|🎨|⚙️|🖱️|⌨️|🔐|🎥|⏸|⏻|●|✓|✗|⚠️" sigtouch/ui/` 为空(test_no_emoji 固化)。
4. 人工 QA:`docs/manual-qa.md` 第 18 项。
5. 纯度 grep 与 PyQt grep 为空;硬契约(GestureProgress/update_hand 签名等)未破坏。

## 后续工作(不在本计划)

- 深色模式;动画缓动库;托盘状态图标重绘。
