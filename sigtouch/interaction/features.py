"""从 HandFrame 提取手势判定特征。纯 Python,只依赖标准库。"""
import math

from sigtouch.perception.types import HandFrame

WRIST = 0
THUMB_TIP = 4
THUMB_MCP = 2
THUMB_IP = 3
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_PIP = 14
RING_TIP = 16
PINKY_MCP = 17
PINKY_PIP = 18
PINKY_TIP = 20


def _dist(a, b) -> float:
    return math.dist(a[:2], b[:2])


def palm_size(hand: HandFrame) -> float:
    return _dist(hand.landmarks[WRIST], hand.landmarks[MIDDLE_MCP])


def pinch_ratio(hand: HandFrame, tip_idx: int) -> float:
    """拇指尖到指定指尖的距离,按手掌尺寸归一化(适应远近)。"""
    return _dist(hand.landmarks[THUMB_TIP], hand.landmarks[tip_idx]) / palm_size(hand)


def _finger_extended(hand: HandFrame, tip_idx: int, pip_idx: int) -> bool:
    lm = hand.landmarks
    return _dist(lm[tip_idx], lm[WRIST]) > _dist(lm[pip_idx], lm[WRIST])


def fingers_extended(hand: HandFrame) -> tuple[bool, bool, bool, bool]:
    """(食指, 中指, 无名指, 小指) 是否伸直。"""
    return (_finger_extended(hand, INDEX_TIP, INDEX_PIP),
            _finger_extended(hand, MIDDLE_TIP, MIDDLE_PIP),
            _finger_extended(hand, RING_TIP, RING_PIP),
            _finger_extended(hand, PINKY_TIP, PINKY_PIP))


def palm_facing_camera(hand: HandFrame) -> bool:
    """腕→食指根 与 腕→小指根 的叉积符号判定掌心朝向。
    约定基于镜像画面、图像坐标 y 向下;由 tests/hand_fixtures.py 的姿态固定该约定,
    真实摄像头下的符号在调试预览窗中人工复核。"""
    lm = hand.landmarks
    v1 = (lm[INDEX_MCP][0] - lm[WRIST][0], lm[INDEX_MCP][1] - lm[WRIST][1])
    v2 = (lm[PINKY_MCP][0] - lm[WRIST][0], lm[PINKY_MCP][1] - lm[WRIST][1])
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    return cross > 0 if hand.handedness == "Right" else cross < 0


def bbox_area(hand: HandFrame) -> float:
    xs = [p[0] for p in hand.landmarks]
    ys = [p[1] for p in hand.landmarks]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def anchor_point(hand: HandFrame) -> tuple[float, float]:
    """光标锚点:食指指尖——光标始终钉在影子的食指上。"""
    x, y, _ = hand.landmarks[INDEX_TIP]
    return (x, y)


def is_thumbs_up(hand: HandFrame) -> bool:
    """竖大拇指:拇指伸直指向画面上方,其余四指弯曲握拳。

    约定镜像画面、图像坐标 y 向下——"拇指竖起"=拇指尖(4)的 y 明显小于
    拇指根(2)与腕(0)(更靠画面上方)。四指弯曲用指尖到腕距离 ≤ 指根到腕距离判定
    (与 _finger_extended 相反)。用 tests/hand_fixtures.thumbs_up 固定约定。
    """
    lm = hand.landmarks
    # 四指全部弯曲
    if any(fingers_extended(hand)):
        return False
    # 拇指伸直:尖到腕距离 > 指根到腕距离(余量 1.05 防抖)
    if _dist(lm[THUMB_TIP], lm[WRIST]) <= _dist(lm[THUMB_MCP], lm[WRIST]) * 1.05:
        return False
    # 拇指向上:尖的 y 比指根小至少 0.6 倍掌尺寸
    upward = lm[THUMB_MCP][1] - lm[THUMB_TIP][1]
    return upward > palm_size(hand) * 0.6
