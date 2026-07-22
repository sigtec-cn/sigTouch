"""合成 21 关键点手部。约定:归一化图像坐标,x 右 y 下;右手掌心朝摄像头,指尖朝上。
基准张开手:手腕(0.50,0.60),手掌尺寸(腕到中指根)=0.10。"""
from sigtouch.perception.types import HandFrame

_BASE = {
    0: (0.50, 0.60),                                            # wrist
    1: (0.455, 0.575), 2: (0.43, 0.55), 3: (0.415, 0.52), 4: (0.40, 0.49),   # thumb
    5: (0.47, 0.50), 6: (0.47, 0.46), 7: (0.47, 0.43), 8: (0.47, 0.40),      # index
    9: (0.50, 0.50), 10: (0.50, 0.45), 11: (0.50, 0.42), 12: (0.50, 0.39),   # middle
    13: (0.53, 0.50), 14: (0.53, 0.46), 15: (0.53, 0.43), 16: (0.53, 0.40),  # ring
    17: (0.56, 0.51), 18: (0.56, 0.47), 19: (0.56, 0.45), 20: (0.56, 0.43),  # pinky
}
_CX, _CY = 0.50, 0.55  # 缩放中心


def open_hand(dx=0.0, dy=0.0, scale=1.0, handedness="Right") -> HandFrame:
    lms = []
    for i in range(21):
        x, y = _BASE[i]
        lms.append(((x - _CX) * scale + _CX + dx, (y - _CY) * scale + _CY + dy, 0.0))
    return HandFrame(landmarks=lms, handedness=handedness)


def _with(hand: HandFrame, changes: dict) -> HandFrame:
    lms = list(hand.landmarks)
    for i, (x, y) in changes.items():
        lms[i] = (x, y, 0.0)
    return HandFrame(landmarks=lms, handedness=hand.handedness)


def _get_scale_dx_dy(**kw):
    """Extract scale, dx, dy from kwargs with defaults."""
    return kw.get('scale', 1.0), kw.get('dx', 0.0), kw.get('dy', 0.0)


def _transform_landmark(x_base, y_base, scale, dx, dy):
    """Transform a base landmark position using scale and offset."""
    return ((x_base - _CX) * scale + _CX + dx, (y_base - _CY) * scale + _CY + dy)


def pinch_index(**kw) -> HandFrame:
    """拇指+食指捏合,其余三指弯曲(普通捏合,区别于 OK)。"""
    h = open_hand(**kw)
    scale, dx, dy = _get_scale_dx_dy(**kw)
    ix, iy, _ = h.landmarks[8]

    return _with(h, {4: (ix - 0.005 * scale, iy),
                     12: _transform_landmark(0.50, 0.55, scale, dx, dy),
                     16: _transform_landmark(0.53, 0.55, scale, dx, dy),
                     20: _transform_landmark(0.56, 0.56, scale, dx, dy)})


def pinch_middle(**kw) -> HandFrame:
    """拇指+中指捏合,食指/无名指/小指弯曲。"""
    h = open_hand(**kw)
    scale, dx, dy = _get_scale_dx_dy(**kw)
    mx, my, _ = h.landmarks[12]

    return _with(h, {4: (mx - 0.005 * scale, my),
                     8: _transform_landmark(0.47, 0.55, scale, dx, dy),
                     16: _transform_landmark(0.53, 0.55, scale, dx, dy),
                     20: _transform_landmark(0.56, 0.56, scale, dx, dy)})


def three_pinch(**kw) -> HandFrame:
    """拇指+食指+中指三指捻住,无名指/小指弯曲(滚动手势)。
    覆盖坐标相对变换后的手计算,保证 dx/dy/scale 参数对指尖同样生效
    (滚动测试依赖 dy 平移让食指尖 y 逐帧变化)。"""
    h = open_hand(**kw)
    scale, _, _ = _get_scale_dx_dy(**kw)
    ix, iy, _ = h.landmarks[8]   # 食指尖(已变换)
    wx, wy, _ = h.landmarks[0]   # 手腕(已变换)
    return _with(h, {4: (ix + 0.005 * scale, iy), 12: (ix + 0.02 * scale, iy + 0.005 * scale),
                     16: (wx + 0.03 * scale, wy - 0.05 * scale), 20: (wx + 0.06 * scale, wy - 0.04 * scale)})


def thumbs_left_up_diagonal(**kw) -> HandFrame:
    """拇指左上对角:拇指尖相对指根同时向左(-0.07*scale)和向上(-0.07*scale)偏移,
    使 leftward≈upward≈0.7×palm_size,均超过 0.6×palm 阈值——is_thumbs_left 与
    is_thumbs_up 同时判 True。用于模拟"保持 THUMBS_LEFT 时拇指略微上飘"的边界抖动,
    验证保持态不会被误判回 IDLE(见 tests/test_thumbs_left.py)。"""
    h = open_hand(**kw)
    scale, dx, dy = _get_scale_dx_dy(**kw)
    wx, wy, _ = h.landmarks[0]   # 腕
    mcp_x, mcp_y = wx - 0.03 * scale, wy - 0.01 * scale
    tip_x, tip_y = mcp_x - 0.07 * scale, mcp_y - 0.07 * scale
    changes = {
        1: (wx - 0.015 * scale, wy - 0.005 * scale),
        2: (mcp_x, mcp_y),
        3: (mcp_x - 0.045 * scale, mcp_y - 0.035 * scale),
        4: (tip_x, tip_y),   # 拇指尖,左上对角
        # 四指弯曲:指尖收回靠近腕(指尖到腕距离 < 指根到腕距离)
        8: (wx - 0.01 * scale, wy - 0.02 * scale),
        12: (wx + 0.0 * scale, wy - 0.02 * scale),
        16: (wx + 0.03 * scale, wy - 0.02 * scale),
        20: (wx + 0.06 * scale, wy - 0.01 * scale),
    }
    return _with(h, changes)


def ok_pose(**kw) -> HandFrame:
    """OK 手势:拇指食指成环,中/无名/小指伸直(仅移动拇指)。"""
    h = open_hand(**kw)
    scale = kw.get('scale', 1.0)
    ix, iy, _ = h.landmarks[8]
    return _with(h, {4: (ix - 0.005 * scale, iy)})


def thumbs_up(**kw) -> HandFrame:
    """竖大拇指:拇指伸直指向画面上方(y 更小),食/中/无名/小指弯曲握拳。"""
    h = open_hand(**kw)
    scale, dx, dy = _get_scale_dx_dy(**kw)
    wx, wy, _ = h.landmarks[0]   # 腕
    # 拇指:各节沿"向上"排列,尖明显在根上方(掌尺寸 scale=0.10*scale,上方阈值 0.6)
    changes = {
        1: (wx - 0.04 * scale, wy - 0.06 * scale),
        2: (wx - 0.045 * scale, wy - 0.10 * scale),
        3: (wx - 0.05 * scale, wy - 0.14 * scale),
        4: (wx - 0.05 * scale, wy - 0.18 * scale),   # 拇指尖,最高
        # 四指弯曲:指尖收回靠近腕(指尖到腕距离 < 指根到腕距离)
        8: (wx - 0.01 * scale, wy - 0.02 * scale),
        12: (wx + 0.0 * scale, wy - 0.02 * scale),
        16: (wx + 0.03 * scale, wy - 0.02 * scale),
        20: (wx + 0.06 * scale, wy - 0.01 * scale),
    }
    return _with(h, changes)


def thumbs_left(**kw) -> HandFrame:
    """拇指向左:拇指伸直指向画面左侧(x 更小),食/中/无名/小指弯曲握拳。"""
    h = open_hand(**kw)
    scale, dx, dy = _get_scale_dx_dy(**kw)
    wx, wy, _ = h.landmarks[0]   # 腕
    mcp_x, mcp_y = wx - 0.03 * scale, wy - 0.01 * scale
    tip_x = mcp_x - 0.08 * scale  # tip 在 mcp 左侧 palm(0.10*scale)×0.8 处,y 同高
    changes = {
        1: (wx - 0.015 * scale, wy - 0.005 * scale),
        2: (mcp_x, mcp_y),
        3: (mcp_x - 0.045 * scale, mcp_y),
        4: (tip_x, mcp_y),   # 拇指尖,最靠左
        # 四指弯曲:指尖收回靠近腕(指尖到腕距离 < 指根到腕距离)
        8: (wx - 0.01 * scale, wy - 0.02 * scale),
        12: (wx + 0.0 * scale, wy - 0.02 * scale),
        16: (wx + 0.03 * scale, wy - 0.02 * scale),
        20: (wx + 0.06 * scale, wy - 0.01 * scale),
    }
    return _with(h, changes)
