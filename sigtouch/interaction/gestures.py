"""手势状态机。消费 HandFrame 序列,产出离散输入事件。纯 Python。

阈值全部按手掌尺寸归一化;捏合判定用进入/退出双阈值(滞回);
离散事件(点击/回车/退格)有独立冷却窗口防连发。
"""
import math
from dataclasses import dataclass
from enum import Enum, auto

from sigtouch.config import Config
from sigtouch.interaction import features as F
from sigtouch.perception.types import HandFrame


class EventKind(Enum):
    LEFT_CLICK = auto()
    RIGHT_CLICK = auto()
    DRAG_START = auto()
    DRAG_END = auto()
    SCROLL = auto()      # value = 滚轮行数, 正=向上
    ENTER = auto()
    BACKSPACE = auto()


@dataclass(frozen=True)
class Event:
    kind: EventKind
    value: float = 0.0


class _State(Enum):
    IDLE = auto()
    INDEX_PINCH = auto()   # 捏合中,未定性(点击 or 拖拽)
    DRAGGING = auto()
    MIDDLE_PINCH = auto()
    SCROLLING = auto()
    OK_PENDING = auto()    # Task 7
    OK_FIRED = auto()      # Task 7

_TELEPORT_THRESHOLD = 0.25  # 归一化锚点单帧跳变超过此值视为换手/瞬移

_PINCH_STATES = frozenset({_State.INDEX_PINCH, _State.DRAGGING,
                           _State.MIDDLE_PINCH, _State.SCROLLING,
                           _State.OK_PENDING, _State.OK_FIRED})

_GESTURE_TOGGLE = {
    EventKind.LEFT_CLICK: "gestures/left_click",
    EventKind.RIGHT_CLICK: "gestures/right_click",
    EventKind.DRAG_START: "gestures/left_click",
    EventKind.DRAG_END: "gestures/left_click",
    EventKind.SCROLL: "gestures/scroll",
    EventKind.ENTER: "gestures/enter",
    EventKind.BACKSPACE: "gestures/backspace",
}


class GestureStateMachine:
    def __init__(self, cfg: Config):
        self._c = cfg
        self._state = _State.IDLE
        self._state_t = 0
        self._cooldown_until: dict[EventKind, int] = {}
        self._scroll_last_y: float | None = None
        self._scroll_accum = 0.0
        self._push_history: list[tuple[int, float]] = []  # Task 7
        self._last_anchor: tuple[float, float] | None = None
        self.feedback: str | None = None                   # Task 7 赋值

    @property
    def pinching(self) -> bool:
        return self._state in _PINCH_STATES

    def _cooled(self, kind: EventKind, t_ms: int) -> bool:
        return t_ms >= self._cooldown_until.get(kind, 0)

    def _emit(self, out: list[Event], kind: EventKind, t_ms: int,
              value: float = 0.0, cooldown: bool = False) -> None:
        if not self._c.get(_GESTURE_TOGGLE[kind]):
            return
        if cooldown:
            self._cooldown_until[kind] = t_ms + self._c.get("interaction/cooldown_ms")
        out.append(Event(kind, value))

    def _to(self, state: "_State", t_ms: int) -> None:
        self._state = state
        self._state_t = t_ms

    def update(self, hand: HandFrame | None, t_ms: int) -> list[Event]:
        out: list[Event] = []
        self.feedback = None
        if hand is None:
            if self._state is _State.DRAGGING:
                self._emit(out, EventKind.DRAG_END, t_ms)
            self._to(_State.IDLE, t_ms)
            self._scroll_last_y = None
            self._push_history.clear()
            self._last_anchor = None
            return out

        anchor = F.anchor_point(hand)
        if self._last_anchor is not None and \
                math.dist(anchor, self._last_anchor) > _TELEPORT_THRESHOLD:
            # 锚点瞬移:多人场景换手或检测跳变——按手部丢失处理,吸收不连续
            if self._state is _State.DRAGGING:
                self._emit(out, EventKind.DRAG_END, t_ms)
            self._to(_State.IDLE, t_ms)
            self._scroll_last_y = None
            self._push_history.clear()
            self._last_anchor = anchor
            return out
        self._last_anchor = anchor

        enter = self._c.get("interaction/pinch_enter")
        exit_ = self._c.get("interaction/pinch_exit")
        click_max = self._c.get("interaction/click_max_ms")
        idx_r = F.pinch_ratio(hand, F.INDEX_TIP)
        mid_r = F.pinch_ratio(hand, F.MIDDLE_TIP)
        idx_pinch, mid_pinch = idx_r < enter, mid_r < enter
        _, mid_ext, ring_ext, pinky_ext = F.fingers_extended(hand)

        if self._state is _State.IDLE:
            self._check_push(hand, t_ms, out)  # Task 7 实现,本 Task 为空操作
            if idx_pinch and mid_ext and ring_ext and pinky_ext:
                self._to(_State.OK_PENDING, t_ms)      # OK track (Task 7)
            elif idx_pinch and mid_pinch:
                self._to(_State.SCROLLING, t_ms)
                self._scroll_last_y = hand.landmarks[F.INDEX_TIP][1]
                self._scroll_accum = 0.0
            elif idx_pinch:
                self._to(_State.INDEX_PINCH, t_ms)
            elif mid_pinch:
                self._to(_State.MIDDLE_PINCH, t_ms)

        elif self._state is _State.INDEX_PINCH:
            if mid_pinch:  # 中指跟进 → 升级为滚动
                self._to(_State.SCROLLING, t_ms)
                self._scroll_last_y = hand.landmarks[F.INDEX_TIP][1]
                self._scroll_accum = 0.0
            elif idx_r > exit_:
                if t_ms - self._state_t <= click_max and \
                        self._cooled(EventKind.LEFT_CLICK, t_ms):
                    self._emit(out, EventKind.LEFT_CLICK, t_ms, cooldown=True)
                self._to(_State.IDLE, t_ms)
            elif t_ms - self._state_t > click_max:
                self._emit(out, EventKind.DRAG_START, t_ms)
                self._to(_State.DRAGGING, t_ms)

        elif self._state is _State.DRAGGING:
            if idx_r > exit_:
                self._emit(out, EventKind.DRAG_END, t_ms)
                self._to(_State.IDLE, t_ms)

        elif self._state is _State.MIDDLE_PINCH:
            if mid_r > exit_:
                if t_ms - self._state_t <= click_max and \
                        self._cooled(EventKind.RIGHT_CLICK, t_ms):
                    self._emit(out, EventKind.RIGHT_CLICK, t_ms, cooldown=True)
                self._to(_State.IDLE, t_ms)

        elif self._state is _State.SCROLLING:
            if idx_r > exit_ or mid_r > exit_:
                self._to(_State.IDLE, t_ms)
                self._scroll_last_y = None
            else:
                y = hand.landmarks[F.INDEX_TIP][1]
                if self._scroll_last_y is not None:
                    # y 向下为正;上移(y 减小)→ 正滚动量(向上滚)
                    self._scroll_accum += (self._scroll_last_y - y) * \
                        self._c.get("interaction/scroll_gain")
                self._scroll_last_y = y
                lines = int(self._scroll_accum)
                if lines != 0:
                    self._scroll_accum -= lines
                    self._emit(out, EventKind.SCROLL, t_ms, value=float(lines))

        elif self._state in (_State.OK_PENDING, _State.OK_FIRED):
            self._update_ok(hand, t_ms, out, idx_r, exit_,
                            mid_ext and ring_ext and pinky_ext)

        return out

    # ---- Task 7 填充下面两个方法 ----
    def _check_push(self, hand: HandFrame, t_ms: int, out: list[Event]) -> None:
        """张开手掌、掌心朝屏,包围盒面积在窗口内快速增大 → 退格。"""
        if not (all(F.fingers_extended(hand)) and F.palm_facing_camera(hand)):
            self._push_history.clear()
            return
        area = F.bbox_area(hand)
        window = self._c.get("interaction/push_window_ms")
        self._push_history.append((t_ms, area))
        self._push_history = [(t, a) for t, a in self._push_history
                              if t_ms - t <= window]
        base = min(a for _, a in self._push_history)
        if base > 0 and area / base >= self._c.get("interaction/push_area_ratio") \
                and self._cooled(EventKind.BACKSPACE, t_ms):
            self._emit(out, EventKind.BACKSPACE, t_ms, cooldown=True)
            if out and out[-1].kind is EventKind.BACKSPACE:
                self.feedback = "⌫"
            self._push_history.clear()

    def _update_ok(self, hand: HandFrame, t_ms: int, out: list[Event],
                   idx_r: float, exit_: float, others_ext: bool) -> None:
        pose_held = idx_r < exit_ and others_ext
        if not pose_held:
            self._to(_State.IDLE, t_ms)  # 姿态破坏 → 回位并重新武装
            return
        if self._state is _State.OK_PENDING and \
                t_ms - self._state_t >= self._c.get("interaction/ok_hold_ms") and \
                self._cooled(EventKind.ENTER, t_ms):
            self._emit(out, EventKind.ENTER, t_ms, cooldown=True)
            if out and out[-1].kind is EventKind.ENTER:
                self.feedback = "⏎"
            self._to(_State.OK_FIRED, t_ms)  # 已触发,保持姿态不重复
