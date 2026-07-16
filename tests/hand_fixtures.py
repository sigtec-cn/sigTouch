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


_CURL = {12: (0.50, 0.55), 16: (0.53, 0.55), 20: (0.56, 0.56)}  # 中/无名/小指弯曲


def pinch_index(**kw) -> HandFrame:
    """拇指+食指捏合,其余三指弯曲(普通捏合,区别于 OK)。"""
    h = open_hand(**kw)
    scale = kw.get('scale', 1.0)
    dx = kw.get('dx', 0.0)
    dy = kw.get('dy', 0.0)
    ix, iy, _ = h.landmarks[8]

    # Transform curled positions using the same scale/offset
    def transform(x_base, y_base):
        return ((x_base - _CX) * scale + _CX + dx, (y_base - _CY) * scale + _CY + dy)

    return _with(h, {4: (ix - 0.005 * scale, iy),
                     12: transform(0.50, 0.55),
                     16: transform(0.53, 0.55),
                     20: transform(0.56, 0.56)})


def pinch_middle(**kw) -> HandFrame:
    """拇指+中指捏合,食指/无名指/小指弯曲。"""
    h = open_hand(**kw)
    scale = kw.get('scale', 1.0)
    dx = kw.get('dx', 0.0)
    dy = kw.get('dy', 0.0)
    mx, my, _ = h.landmarks[12]

    # Transform curled positions using the same scale/offset
    def transform(x_base, y_base):
        return ((x_base - _CX) * scale + _CX + dx, (y_base - _CY) * scale + _CY + dy)

    return _with(h, {4: (mx - 0.005 * scale, my),
                     8: transform(0.47, 0.55),
                     16: transform(0.53, 0.55),
                     20: transform(0.56, 0.56)})


def three_pinch(**kw) -> HandFrame:
    """拇指+食指+中指三指捻住,无名指/小指弯曲(滚动手势)。
    覆盖坐标相对变换后的手计算,保证 dx/dy/scale 参数对指尖同样生效
    (滚动测试依赖 dy 平移让食指尖 y 逐帧变化)。"""
    h = open_hand(**kw)
    ix, iy, _ = h.landmarks[8]   # 食指尖(已变换)
    wx, wy, _ = h.landmarks[0]   # 手腕(已变换)
    return _with(h, {4: (ix + 0.005, iy), 12: (ix + 0.02, iy + 0.005),
                     16: (wx + 0.03, wy - 0.05), 20: (wx + 0.06, wy - 0.04)})


def ok_pose(**kw) -> HandFrame:
    """OK 手势:拇指食指成环,中/无名/小指伸直(仅移动拇指)。"""
    h = open_hand(**kw)
    scale = kw.get('scale', 1.0)
    ix, iy, _ = h.landmarks[8]
    return _with(h, {4: (ix - 0.005 * scale, iy)})
