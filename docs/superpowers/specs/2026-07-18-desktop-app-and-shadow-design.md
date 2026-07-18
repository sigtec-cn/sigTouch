# SigTouch v1.2 设计文档:桌面 App、影子渲染与光标锚定

日期:2026-07-18
状态:已确认
关联:v1 `2026-07-16-sigtouch-design.md`,v1.1 `2026-07-17-permissions-and-ci-design.md`

## 1. 需求与决策

| # | 需求 | 决策 |
|---|---|---|
| 1 | 编译产物是桌面 App | macOS 增加 PyInstaller `BUNDLE` 产出 `dist/SigTouch.app`;Windows/Linux 维持现状(exe/onedir 已是桌面应用形态) |
| 2 | 手部影子始终置顶所有窗口 | macOS 用 pyobjc-Cocoa 设 NSWindow level+collectionBehavior(覆盖全屏 App 与所有空间);三平台每秒 `raise_()` 兜底 |
| 3 | 鼠标始终在食指上 | 光标锚点改为食指指尖;Overlay 影子整体平移使食指尖像素点与光标重合(影子跟随光标) |
| 4 | 设置选择左手/右手,仅用一只手 | 配置 `interaction/active_hand`(Right 默认/Left);管线 `num_hands=2` 仅取 handedness 匹配者,不匹配视为无手 |
| 5 | 影子/剪影效果而非骨架 | QPainterPath 实心手形填充;**深色影子**默认(`#000000` @ 0.35);颜色控件补进设置界面 |

## 2. macOS .app 打包

`packaging/sigtouch.spec` 在 `COLLECT` 后追加:

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

- `.app` 拥有独立 TCC 身份:系统权限面板显示 "SigTouch",与 v1.1 权限引导配套(`NSCameraUsageDescription` 是摄像头授权弹窗的必要条件)。
- 不设 `LSUIElement`(保留 Dock 图标,便于用户找到应用;托盘化隐藏 Dock 留作后续可选项)。
- `release.yml` macOS 打包改为 `cd dist && zip -qry ../SigTouch-<tag>-macos-arm64.zip SigTouch.app`。
- README/packaging README 同步:`xattr -cr SigTouch.app` 后双击或 `open SigTouch.app`。
- 依赖变更:`pyobjc-framework-Cocoa>=10.0; sys_platform == 'darwin'`(第 3 节也用)。

## 3. 影子全窗口置顶

新增 `sigtouch/ui/native.py`:

```python
def pin_window_topmost(widget) -> None
```

- darwin:经 `widget.winId()` 取 NSView → `.window()` 得 NSWindow,设:
  - `setLevel_(1000)`(NSScreenSaverWindowLevel,高于全屏窗口层);
  - `setCollectionBehavior_(CanJoinAllSpaces | FullScreenAuxiliary | Stationary)`(跟随所有空间、可悬浮于全屏 App 之上)。
  - 任何异常 fail-open(仅 `logging.warning`),保持 Qt 置顶行为。
- 非 darwin:no-op(Qt `WindowStaysOnTopHint` 已足够)。
- 调用点:`OverlayWindow.apply_screen()` 在 `show()` 之后调用。
- 三平台兜底:`SigTouchApp._check_watchdog`(1s tick)中,若 overlay 可见则 `raise_()`,防止被后开窗口覆盖。

## 4. 光标锚定食指 + 影子跟随光标

### 4.1 锚点

`features.anchor_point(hand)` 改为返回**食指指尖**坐标(`landmarks[INDEX_TIP][:2]`)。捏合动作会引起指尖小幅移动,由既有捏合冻结(150ms)吸收,点击位置稳定性不回退。

### 4.2 影子对齐光标

Overlay 渲染管线改为"光标对齐"模式:

```
scaled = scaled_points(landmarks, w, h, scale)      # 现有:归一化→像素,绕质心缩放
dx, dy = cursor_px - scaled[INDEX_TIP]              # 新:整体平移量
final = [(x+dx, y+dy) for (x, y) in scaled]         # 食指尖恰好落在光标上
```

- `OverlayWindow.update_hand(hand, scale, feedback, cursor_px)` 新增第 4 参数(overlay 本地坐标,即 mapper 输出的目标屏内像素;多显示器时 overlay 与光标同屏,坐标系一致)。
- `SigTouchApp._on_result`:mapper 输出 `(x, y)` 后同时用于注入(加屏幕原点偏移)与 overlay(本地坐标直传)。注入被降级门控跳过时(无辅助功能权限),overlay 仍用 mapper 输出对齐——影子行为与权限无关。
- 手存在但光标冻结期间:mapper 返回冻结坐标,影子随之停住(预期行为)。
- 新增纯函数 `align_to_cursor(points, index_tip_idx, cursor_px) -> list[tuple]` 供单测。

## 5. 左右手选择

- 配置:`interaction/active_hand: "Right"`(默认;可选 "Left")。
- 设置-交互页顶部新增"控制手"下拉(右手/左手),经 `_fields` 注册表绑定(combo 存字符串:注册 getter/setter 做 index↔值映射,或用 `currentText` 映射表——实现取 QComboBox + userData)。
- 感知管线:`HandLandmarkerOptions(num_hands=2)`;新增纯函数:

```python
def select_hand(hands: list[tuple[str, list[Landmark]]], wanted: str) -> list[Landmark] | None
    # hands: [(handedness_label, landmarks), ...];返回匹配 wanted 的第一只,无匹配返回 None
```

- `PerceptionPipeline(frame_width, fov_deg, models_dir=None, active_hand="Right")`;`VisionThread` 从 cfg 读取并传入;设置 Apply 已有的 `_restart_vision()` 使变更即时生效。
- 镜像画面下 MediaPipe handedness 标签与真实手一致;调试预览窗在骨架旁显示 `hand=Left/Right` 标签供真机核对(若真机发现标签反向,修 `select_hand` 调用处的映射并同步夹具约定)。

## 6. 影子/剪影渲染

`OverlayWindow.paintEvent` 重写渲染核心,新增模块级纯函数:

```python
def silhouette_path(points: list[tuple[float, float]], palm_size_px: float) -> QPainterPath
```

- 五条手指链(现有 `_FINGER_CHAINS`)各构建折线 QPainterPath,用 `QPainterPathStroker`(RoundCap/RoundJoin)描边成闭合形:拇指/手指宽度 ≈ `palm_size_px × 0.28`,掌臂链(0-17)宽度 ≈ `palm_size_px × 0.55`;
- 掌心多边形(`_PALM_LOOP`)路径;全部 `united()` 合成单一实心手形;
- 填充 `display/overlay_color`(**新默认 `#000000`**)+ `display/overlay_opacity`(默认 0.35 不变),`Qt.NoPen`;
- `palm_size_px` 由缩放后的 WRIST→MIDDLE_MCP 像素距离计算,天然随距离缩放;
- 反馈图标(⏎/⌫)保留(深色影子上改用带描边的高对比文本);
- 设置-显示页新增"影子颜色"按钮(QColorDialog 选色,`_fields` 注册 getter/setter 存 hex 字符串)。

`DEFAULTS["display/overlay_color"]` 改为 `"#000000"`(既有用户若 QSettings 已存白色则维持其存量值——可接受)。

## 7. 测试策略

- `features.anchor_point`:更新断言为食指尖(现有测试改)。
- `align_to_cursor` / `silhouette_path`:纯函数单测(平移后食指尖==光标;silhouette 路径非空、包含指尖点、面积随 palm_size 增大)。
- `select_hand`:匹配/不匹配/空列表/两手同标签取第一只。
- 设置对话框:active_hand 与 overlay_color 控件 roundtrip(offscreen)。
- app:扩展 harness 断言 `update_hand` 收到 mapper 坐标(monkeypatch overlay 记录调用)。
- `.app` 打包、置顶层级、左右手真机识别:manual-qa 追加第 12 项(打包 .app 双击启动、影子盖住全屏视频、切左手后仅左手可控、光标钉在影子食指尖)。

## 8. 明确不做(v1.2)

- Windows/Linux 的原生窗口层级增强(Qt 置顶 + raise 兜底已足够,遇到具体压层问题再处理)。
- 双手同时参与(仍单手控制)。
- 影子柔化边缘/模糊(选定硬边深色剪影)。
- Dock 图标隐藏(LSUIElement)。
