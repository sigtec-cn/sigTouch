# SigTouch v1.9 设计文档:手势动画重做、拇指向左退格与 shadcn 界面

日期:2026-07-22
状态:已确认
关联:上游提交 4b9c1d0(计时捏合/进度环)、6963bc7(七项改进);v1.3 主题、v1.5 状态明示

## 1. 四项需求与决策

| # | 需求 | 决策 |
|---|---|---|
| 1 | 触发动画以鼠标为中心,优化视觉(现在又大又丑) | 进度环/图标**正中心 = cursor_px**(去掉右上偏移);尺寸改为**固定逻辑像素**(不随手掌/scale 缩放);细描边 shadcn 质感 |
| 2 | 退格改为大拇指向左(两手同规则) | 新手势 `is_thumbs_left`,**用户视角的左**(镜像画面 x 减小方向);整体替换现有"推手"检测(面积增长机制删除) |
| 3 | 所有触发计时默认 1500ms,均可调 | `pinch_hold_ms`(已 1500)、`thumbs_up_hold_ms` 800→**1500**、新 `thumbs_left_hold_ms`=**1500**(替代 push_hold_ms);滑杆统一 500–3000ms |
| 4 | 设置页 shadcn 风格,icon 全用 lucide,不用 emoji | 主题改 **zinc 中性色板 + 黑色主按钮**(shadcn 默认);新模块 `ui/lucide.py` 内嵌 lucide SVG(ISC 许可)渲染 QIcon;设置导航/权限向导/托盘菜单的 emoji 与 ✓✗⚠️● 全部替换 |

## 2. 触发动画重做(`sigtouch/ui/overlay.py`)

现状问题:锚点在光标右上 `cursor + max(28, palm_px*0.5)`,尺寸 `max(14, palm_px*0.32)*scale`——随手掌与距离缩放,大屏/近距下巨大。

新设计:
- **锚点**:`(ox, oy) = cursor_px`(正中心);无 cursor 时不绘制进度(替代原 (0,0) 回退)。
- **尺寸常量**(逻辑像素,不乘 scale/palm):环半径 `_RING_RADIUS = 22`;描边宽 `_RING_STROKE = 3`;图标绘制区 `_GLYPH_SIZE = 18`(环内居中)。
- **视觉(shadcn 质感)**:
  - 轨道:整圆,`rgba(24,24,27,0.25)`(zinc-900 低透明)描边 3px;
  - 进度弧:白色 `rgba(255,255,255,0.95)` 3px,自 12 点顺时针,圆头端帽;
  - 图标(enter ↵ / backspace ←)在环内以 2px 细线随 fraction 描画,白色;
  - 触发闪烁:环半径 22→30 扩散 + 透明度衰减,160ms(柔化,替代现白色脉冲);
  - 左右键区分:右键在环旁 4 点方向加 3px 白点(避免引入文字)。
- 保留 `GestureProgress` 数据结构与 `update_hand` 签名(仅绘制层改动)。
- 退格图标笔画改为「←」左箭头(与新手势语义一致,替代箭头+×)。

## 3. 拇指向左退格

### 3.1 特征(`sigtouch/interaction/features.py`)

```python
def is_thumbs_left(hand) -> bool
    # 四指全弯曲(not any(fingers_extended))
    # 拇指伸直:tip 到腕距 > mcp 到腕距 × 1.05(与 is_thumbs_up 同准)
    # 指向左:thumb_mcp.x - thumb_tip.x > palm_size × 0.6(镜像画面用户视角左 = x 减小)
    # 两手同一规则(不依赖 handedness)
```

与 `is_thumbs_up` 互斥性:各自方向阈值(0.6×palm)保证同一姿态不同时满足;状态机按 up 优先判定。

### 3.2 状态机(`sigtouch/interaction/gestures.py`)

- 删除 PUSH 面积增长机制(`_push_start/_update_push`、`push_area_ratio`、`push_window_ms` 消费代码);
- 新 `THUMBS_LEFT` 状态,与 `THUMBS_UP` 同构:进入 = `is_thumbs_left`;保持 `interaction/thumbs_left_hold_ms` 触发 `BACKSPACE`;`GestureProgress(kind="backspace")` 照常输出;cooldown/开关(`gestures/backspace`)不变;
- config:新增 `interaction/thumbs_left_hold_ms: 1500`;`thumbs_up_hold_ms` 默认改 1500;`push_hold_ms`、`push_area_ratio`、`push_window_ms` 从 DEFAULTS 删除(设置页滑杆同步替换)。

## 4. shadcn 主题与 lucide 图标

### 4.1 色板(`sigtouch/ui/theme.py`,zinc)

| Token | 新值 | 说明 |
|---|---|---|
| BG | `#FAFAFA` | zinc-50 |
| CARD | `#FFFFFF` | |
| BORDER | `#E4E4E7` | zinc-200 |
| TEXT | `#09090B` | zinc-950 |
| TEXT_MUTED | `#71717A` | zinc-500 |
| ACCENT | `#18181B` | zinc-900(主按钮/滑杆/选中态,黑) |
| ACCENT_HOVER | `#27272A` | zinc-800 |
| OK/WARN/DANGER | 不变 | 语义色保留 |

QSS 同步:primary 按钮黑底白字;滑杆已填充段/checkbox 选中 = ACCENT 黑;导航选中左侧竖条黑;radius 卡片 8/控件 6 不变;overlay 进度动画用白色系(见 §2),不受主题影响。

### 4.2 lucide 图标模块(新 `sigtouch/ui/lucide.py`)

- 内嵌所需 lucide 图标的 SVG path 数据(文件头注明 ISC 许可与来源);`icon(name, color=theme.TEXT, size=16) -> QIcon`(QtSvg 渲染,支持 2x 缩放清晰)。
- 首批图标:`camera, hand, palette, settings, mouse-pointer, keyboard, check, x, triangle-alert, rotate-cw, video, shield, power, circle`。

### 4.3 替换点(全部去 emoji/符号)

| 位置 | 现状 | 替换 |
|---|---|---|
| 设置导航 `_NAV_ITEMS` | 📷 ✋ 🎨 ⚙️ 前缀 | `QListWidgetItem` setIcon(camera/hand/palette/settings)+纯文字 |
| 权限向导行图标 | 📷 🖱️ ⌨️ | camera / mouse-pointer / keyboard 图标 QLabel(pixmap) |
| 向导成功横幅 | "✓ 全部权限已就绪…" | check 图标 + 纯文字 |
| 向导重启提示 | "⚠️ 快捷键需重启…" | triangle-alert 图标 + 纯文字;重启按钮加 rotate-cw |
| 向导徽章 | "✓ 已授权"/"✗ 未授权" | check/x 图标 + "已授权"/"未授权" 文字(badge 容器化:图标+QLabel) |
| 托盘菜单 | ⚙️ 🔐 🎥 ⏸ ▶ ⏻ 前缀 | QAction.setIcon(settings/shield/video/…)+纯文字;暂停/恢复用 pause/play(补两枚图标),退出 power |
| 设置状态徽章 `_STATE_TEXT` | ● 前缀 | circle 填充图标(语义色)+ 纯文字 |

测试兼容:现有断言多为"文本包含"(如 `"权限设置" in`、`startswith("✓")`)——徽章断言改为纯文字包含(如 `"已授权" in`),菜单断言已是子串匹配;计划中逐一列明需改的断言。

## 5. 测试策略

- `is_thumbs_left`:左向/右向/未弯指/两手 handedness 无关;与 is_thumbs_up 互斥。
- 状态机:thumbs_left 保持 1500ms 触发 BACKSPACE、提前松开不触发、progress kind="backspace" fraction 递增、cooldown/开关;推手旧测试删除或改写。
- 动画几何:进度绘制中心=cursor_px(单测新纯量常量与锚点计算,或将锚点/尺寸计算抽为纯函数 `progress_geometry(cursor_px) -> (center, radius)` 便于断言);无 cursor 不绘制。
- lucide:`icon()` 返回非空 QIcon、未知名抛 KeyError;全部首批名字可渲染。
- 主题:token 新值断言更新;QSS 冒烟沿用。
- 设置滑杆:thumbs_left_hold_ms 存在、默认 1500、轻量键;push 相关键已删(cfg.get 抛 KeyError)。
- manual-qa 第 18 项:动画居中于光标、观感细腻;拇指向左(两手)退格;三个计时滑杆默认 1500;界面 shadcn 观感、无 emoji。

## 6. 明确不做(v1.9)

- 深色模式(shadcn dark 留后续)。
- 动画缓动曲线库/QPropertyAnimation 重构(保留现有按帧绘制)。
- 托盘状态图标(圆底手掌)重绘——仅菜单项图标化。
