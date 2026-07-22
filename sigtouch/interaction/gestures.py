"""手势状态机。消费 HandFrame 序列,产出离散输入事件 + 结构化判定进度。纯 Python。

阈值全部按手掌尺寸归一化;捏合判定用进入/退出双阈值(滞回);
离散事件(点击/回车/退格)均需"保持判定姿态到指定时长"才触发,并有冷却窗口防连发。
进度经 self.progress 以 GestureProgress 暴露,供 overlay 绘制进度环/图标描画。
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


@dataclass(frozen=True)
class GestureProgress:
    """离散手势的判定进度(供 overlay 画进度环/图标描画)。"""
    kind: str            # "left_click"|"right_click"|"enter"|"backspace"
    fraction: float      # 0.0..1.0 已保持比例,1.0 即触发
    fired: bool = False  # 本帧是否触发(overlay 据此闪烁)


class _State(Enum):
    IDLE = auto()
    INDEX_PINCH = auto()   # 捏合计时中(点击),超时后升级拖拽
    DRAGGING = auto()
    MIDDLE_PINCH = auto()  # 右捏合计时中
    SCROLLING = auto()
    THUMBS_UP = auto()     # 竖大拇指保持中
    PUSH = auto()          # 推手保持中


_TELEPORT_THRESHOLD = 0.25  # 归一化锚点单帧跳变超过此值视为换手/瞬移

# 捏合类状态:控制 CursorMapper 冻结(pinching 语义);离散手势保持态不算捏合
_PINCH_STATES = frozenset({_State.INDEX_PINCH, _State.DRAGGING,
                           _State.MIDDLE_PINCH, _State.SCROLLING})

_HOLD_STATES = frozenset({_State.INDEX_PINCH, _State.DRAGGING,
                          _State.MIDDLE_PINCH, _State.SCROLLING,
                          _State.THUMBS_UP, _State.PUSH})

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
        self._push_history: list[tuple[int, float]] = []
        self._last_anchor: tuple[float, float] | None = None
        self._fired_hold = False                # 当前保持态是否已触发过(防连发)
        self.progress: GestureProgress | None = None

    @property
    def pinching(self) -> bool:
        return self._state in _PINCH_STATES

    # 供 overlay 反馈图标(兼容旧接口):触发帧返回对应符号
    @property
    def feedback(self) -> str | None:
        if self.progress is not None and self.progress.fired:
            return {"left_click": "●", "right_click": "●",
                    "enter": "⏎", "backspace": "⌫"}.get(self.progress.kind)
        return None

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
        if state is not self._state:
            self._fired_hold = False
        self._state = state
        self._state_t = t_ms

    def _reset_transient(self) -> None:
        self._scroll_last_y = None
        self._push_history.clear()

    def update(self, hand: HandFrame | None, t_ms: int) -> list[Event]:
        out: list[Event] = []
        self.progress = None
        if hand is None:
            if self._state is _State.DRAGGING:
                self._emit(out, EventKind.DRAG_END, t_ms)
            self._to(_State.IDLE, t_ms)
            self._reset_transient()
            self._last_anchor = None
            return out

        anchor = F.anchor_point(hand)
        if self._last_anchor is not None and \
                math.dist(anchor, self._last_anchor) > _TELEPORT_THRESHOLD:
            # 锚点瞬移:多人场景换手或检测跳变——按手部丢失处理,吸收不连续
            if self._state is _State.DRAGGING:
                self._emit(out, EventKind.DRAG_END, t_ms)
            self._to(_State.IDLE, t_ms)
            self._reset_transient()
            self._last_anchor = anchor
            return out
        self._last_anchor = anchor

        enter = self._c.get("interaction/pinch_enter")
        exit_ = self._c.get("interaction/pinch_exit")
        idx_r = F.pinch_ratio(hand, F.INDEX_TIP)
        mid_r = F.pinch_ratio(hand, F.MIDDLE_TIP)
        idx_pinch, mid_pinch = idx_r < enter, mid_r < enter
        thumbs_up = F.is_thumbs_up(hand)

        if self._state is _State.IDLE:
            if idx_pinch and mid_pinch:
                self._to(_State.SCROLLING, t_ms)
                self._scroll_last_y = hand.landmarks[F.INDEX_TIP][1]
                self._scroll_accum = 0.0
            elif idx_pinch:
                self._to(_State.INDEX_PINCH, t_ms)
            elif mid_pinch:
                self._to(_State.MIDDLE_PINCH, t_ms)
            elif thumbs_up:
                self._to(_State.THUMBS_UP, t_ms)
            elif self._push_start(hand, t_ms):
                self._to(_State.PUSH, t_ms)

        elif self._state is _State.INDEX_PINCH:
            self._update_index_pinch(hand, t_ms, out, idx_r, mid_pinch, exit_)

        elif self._state is _State.DRAGGING:
            if idx_r > exit_:
                self._emit(out, EventKind.DRAG_END, t_ms)
                self._to(_State.IDLE, t_ms)

        elif self._state is _State.MIDDLE_PINCH:
            self._update_middle_pinch(t_ms, out, mid_r, exit_)

        elif self._state is _State.SCROLLING:
            self._update_scroll(hand, t_ms, out, idx_r, mid_r, exit_)

        elif self._state is _State.THUMBS_UP:
            self._update_thumbs_up(hand, t_ms, out, thumbs_up)

        elif self._state is _State.PUSH:
            self._update_push(hand, t_ms, out)

        return out

    # ---- 各状态 ----
    def _update_index_pinch(self, hand, t_ms, out, idx_r, mid_pinch, exit_):
        hold = self._c.get("interaction/pinch_hold_ms")
        if mid_pinch:  # 中指跟进 → 升级为滚动
            self._to(_State.SCROLLING, t_ms)
            self._scroll_last_y = hand.landmarks[F.INDEX_TIP][1]
            self._scroll_accum = 0.0
            return
        if idx_r > exit_:
            self._to(_State.IDLE, t_ms)  # 提前松开:不触发
            return
        held = t_ms - self._state_t
        frac = min(1.0, held / hold)
        if not self._fired_hold and held >= hold and \
                self._cooled(EventKind.LEFT_CLICK, t_ms):
            self._emit(out, EventKind.LEFT_CLICK, t_ms, cooldown=True)
            self.progress = GestureProgress("left_click", 1.0, fired=True)
            self._fired_hold = True
            # 继续按住 → 进入拖拽:同步按下左键
            self._emit(out, EventKind.DRAG_START, t_ms)
            self._to(_State.DRAGGING, t_ms)
            return
        self.progress = GestureProgress("left_click", frac)

    def _update_middle_pinch(self, t_ms, out, mid_r, exit_):
        hold = self._c.get("interaction/pinch_hold_ms")
        if mid_r > exit_:
            self._to(_State.IDLE, t_ms)
            return
        held = t_ms - self._state_t
        frac = min(1.0, held / hold)
        if not self._fired_hold and held >= hold and \
                self._cooled(EventKind.RIGHT_CLICK, t_ms):
            self._emit(out, EventKind.RIGHT_CLICK, t_ms, cooldown=True)
            self.progress = GestureProgress("right_click", 1.0, fired=True)
            self._fired_hold = True
            return
        self.progress = GestureProgress("right_click", frac)

    def _update_scroll(self, hand, t_ms, out, idx_r, mid_r, exit_):
        if idx_r > exit_ or mid_r > exit_:
            self._to(_State.IDLE, t_ms)
            self._scroll_last_y = None
            return
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

    def _update_thumbs_up(self, hand, t_ms, out, thumbs_up):
        if not thumbs_up:
            self._to(_State.IDLE, t_ms)  # 姿态破坏 → 回位重武装
            return
        hold = self._c.get("interaction/thumbs_up_hold_ms")
        held = t_ms - self._state_t
        frac = min(1.0, held / hold)
        if not self._fired_hold and held >= hold and \
                self._cooled(EventKind.ENTER, t_ms):
            self._emit(out, EventKind.ENTER, t_ms, cooldown=True)
            self.progress = GestureProgress("enter", 1.0, fired=True)
            self._fired_hold = True
            return
        self.progress = GestureProgress("enter", frac)

    def _push_pose(self, hand) -> bool:
        """张开手掌、掌心朝屏(推手的静态姿态前提)。"""
        return all(F.fingers_extended(hand)) and F.palm_facing_camera(hand)

    def _push_start(self, hand, t_ms) -> bool:
        """进入推手:姿态满足且面积在观察窗口内持续增长(确有前推动作)。

        仅凭静态张开姿态不进入——否则普通张开手会长期占住 PUSH 状态,
        阻塞捏合/竖大拇指的进入并污染 pinching 判定。
        """
        if not self._push_pose(hand):
            self._push_history.clear()
            return False
        area = F.bbox_area(hand)
        window = self._c.get("interaction/push_window_ms")
        self._push_history.append((t_ms, area))
        self._push_history = [(t, a) for t, a in self._push_history
                              if t_ms - t <= window]
        base = min(a for _, a in self._push_history)
        return base > 0 and area / base >= self._c.get("interaction/push_area_ratio")

    def _update_push(self, hand, t_ms, out):
        if not self._push_pose(hand):
            self._to(_State.IDLE, t_ms)
            self._push_history.clear()
            return
        # 进入时已确认前推;保持期只要求姿态不破坏,计时到阈值即触发
        hold = self._c.get("interaction/push_hold_ms")
        held = t_ms - self._state_t
        frac = min(1.0, held / hold)
        if not self._fired_hold and held >= hold and \
                self._cooled(EventKind.BACKSPACE, t_ms):
            self._emit(out, EventKind.BACKSPACE, t_ms, cooldown=True)
            self.progress = GestureProgress("backspace", 1.0, fired=True)
            self._fired_hold = True
            return
        self.progress = GestureProgress("backspace", frac)
