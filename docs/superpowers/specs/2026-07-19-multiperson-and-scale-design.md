# SigTouch v1.4 设计文档:多人场景与大屏缩放模型

日期:2026-07-19
状态:已确认
关联:v1 §4.1/4.2(距离与缩放)、v1.2 §5(左右手选择)

## 1. 需求与决策

| 决策 | 结论 |
|---|---|
| 多人时操作者判定 | **离摄像头最近的人**:主脸=瞳距像素最大;操作手=左右手过滤后手掌像素尺寸最大。无跨帧锁定(YAGNI,复杂度高一个量级) |
| 摄像头距屏幕距离 | 新增设置 `display/camera_screen_offset_m`(-2.0~10.0 m,默认 0.0;摄像头在屏幕前为正) |
| 摄像头分辨率 | 不新增:已有 camera/width/height;焦距 = 宽 ÷ 2tan(FOV/2) 已自动参与距离计算 |
| 屏幕分辨率 | 不需要:手影大小按"占屏比例"定义,与分辨率无关 |
| 手影大小倍率 | 新增设置 `display/hand_scale_multiplier`(0.5~3.0,默认 1.0),物理模型后的用户微调 |
| 缩放上限 | 3.0 → 5.0(幕墙场景) |

## 2. 缩放模型升级(`sigtouch/perception/distance.py`)

```
d_screen = d_camera + camera_screen_offset_m          # 人到屏幕的距离
scale = clamp((d_screen / 0.6m) × (24″ / diag_inch) × multiplier, 0.5, 5.0)
```

- `overlay_scale(distance_m, diag_inch, offset_m=0.0, multiplier=1.0) -> float`(签名扩展,原两参调用语义不变:offset 0、倍率 1)。
- `SCALE_MAX` 常量 3.0 → 5.0;`d_screen` 计算后下限保护:`max(0.05, d_screen)`(offset 配置成极端负值时不产生非正距离)。
- 消费方 `app._on_result`:`overlay_scale(dist, diag, cfg.get("display/camera_screen_offset_m"), cfg.get("display/hand_scale_multiplier"))`。

## 3. 多人选择(`sigtouch/perception/pipeline.py`)

### 3.1 主脸

- `FaceLandmarkerOptions(num_faces=3)`(1→3;更多人脸对 CPU 影响可控,超过 3 人取检测器给出的前 3)。
- 新增纯函数:

```python
def select_primary_face(faces: list) -> object | None
    # faces: FaceLandmarker 输出的 face_landmarks 列表
    # 返回瞳距像素最大(虹膜 468/473 距离,归一化坐标下直接比较)的那张脸;空列表 None
```

- 距离估算只用主脸;`face_present = bool(faces)`(任意人脸在场即不挂起,旁观者在场属"有人在用"——语义保持 v1.1)。

### 3.2 操作手

- `HandLandmarkerOptions(num_hands=4)`(2→4:两人×两手的典型上限)。
- `select_hand(hands, wanted)` 升级:候选先按 handedness == wanted 过滤,再取**手掌尺寸最大**者(WRIST 0 到 MIDDLE_MCP 9 的归一化距离,与 features.palm_size 同定义);无匹配返回 None。签名不变,仍返回 landmarks 列表。
- 行为兼容:单人单手时与 v1.2 完全一致(唯一匹配者即最大者)。

### 3.3 调试预览(`sigtouch/ui/preview.py`)

- 叠加一行 `faces=N hands=M`(N/M 为本帧候选计数);需要 `FrameResult` 携带计数 → `types.FrameResult` 新增字段 `face_count: int = 0`、`hand_count: int = 0`(pipeline 填充;既有构造点不受影响,默认 0)。

## 4. 设置界面(`sigtouch/ui/settings_dialog.py` 显示页)

| 项 | 控件 | 键 | 说明文字 |
|---|---|---|---|
| 摄像头到屏幕距离 | QDoubleSpinBox -2.0~10.0, step 0.1, 1 位小数 | `display/camera_screen_offset_m` | 摄像头装在屏幕前方时填正值(米);测的是镜头到屏幕平面的距离 |
| 手影大小倍率 | 滑杆 50–300(%) ↔ /100 | `display/hand_scale_multiplier` | 物理模型算完后的整体微调,大屏看不清就调大 |

两键均为轻量键(不属于 `_RESTART_KEYS`,即时生效走 200ms 合并;overlay_scale 每帧从 cfg 读取,影子实时变化)。

`config.DEFAULTS` 新增:
```python
"display/camera_screen_offset_m": 0.0,
"display/hand_scale_multiplier": 1.0,
```

## 5. 测试策略

- `select_primary_face`:空/单脸/双脸取瞳距大者/并列取首个——合成 face landmarks(仅 468/473 两点有意义)。
- `select_hand` 升级:多候选同 handedness 取掌大者;不同 handedness 过滤;单人行为与 v1.2 等价(回归既有 4 测试,断言微调:duplicate_labels 场景语义从"取第一只"变为"取掌大者"——更新该测试)。
- `overlay_scale`:offset 正/负、倍率、上限 5.0、`d_screen` 下限保护;两参调用向后兼容。
- `FrameResult` 计数字段默认 0(既有测试零改动)。
- 设置 roundtrip + 两键不在 `_RESTART_KEYS` 的即时生效断言。
- manual-qa 第 14 项:双人抢控验证(旁观者在后排同侧手不夺控、走近前排即接管)、幕墙参数标定流程(量摄像头到屏距离→填入→倍率微调)。

## 6. 明确不做(v1.4)

- 跨帧人员锁定/人脸重识别。
- 手与脸的跨模型人员关联(以"最近"代理)。
- 自动标定摄像头到屏距离。
