# tests/test_gestures_pinch.py
from sigtouch.config import Config
from sigtouch.interaction.gestures import Event, EventKind, GestureStateMachine
from tests.hand_fixtures import open_hand, pinch_index, pinch_middle, three_pinch


def _machine(**overrides):
    cfg = Config(backend={})
    for k, v in overrides.items():
        cfg.set(k, v)
    return GestureStateMachine(cfg)


def _run(m, frames):
    """frames: [(hand, t_ms), ...] → 收集全部事件。"""
    out = []
    for hand, t in frames:
        out.extend(m.update(hand, t))
    return out


def _hold(hand_fn, start_ms, end_ms, step=33):
    """生成 [start,end) 时段内保持某姿态的帧序列。"""
    return [(hand_fn(), t) for t in range(start_ms, end_ms, step)]


def test_pinch_held_to_threshold_fires_left_click():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(pinch_index, 33, 1600))
    # 默认 1500ms 触发点击;继续按住即按下左键进入拖拽
    assert evs == [Event(EventKind.LEFT_CLICK), Event(EventKind.DRAG_START)]


def test_pinch_released_early_fires_nothing():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (pinch_index(), 33),
                   (pinch_index(), 800), (open_hand(), 900)])
    assert evs == []  # 未到 1500ms 松开:不点击


def test_pinch_hold_time_configurable():
    m = _machine(**{"interaction/pinch_hold_ms": 600})
    evs = _run(m, [(open_hand(), 0)] + _hold(pinch_index, 33, 700))
    assert evs == [Event(EventKind.LEFT_CLICK), Event(EventKind.DRAG_START)]


def test_held_past_threshold_enters_drag():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(pinch_index, 33, 2000)
                   + [(open_hand(), 2100)])
    # 触发点击→按住进拖拽(DRAG_START)→松开(DRAG_END)
    assert evs == [Event(EventKind.LEFT_CLICK), Event(EventKind.DRAG_START),
                   Event(EventKind.DRAG_END)]


def test_middle_pinch_held_fires_right_click():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(pinch_middle, 33, 1600))
    assert evs == [Event(EventKind.RIGHT_CLICK)]


def test_middle_pinch_released_early_fires_nothing():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (pinch_middle(), 33),
                   (pinch_middle(), 800), (open_hand(), 900)])
    assert evs == []


def test_cooldown_suppresses_rapid_second_click():
    # 用短 hold + 短冷却直接验证冷却机制本身
    m = _machine(**{"interaction/pinch_hold_ms": 300,
                    "interaction/cooldown_ms": 1000})
    first = _run(m, [(open_hand(), 0)] + _hold(pinch_index, 33, 400)
                 + [(open_hand(), 500)])                 # 第一次点击 + 松开
    assert Event(EventKind.LEFT_CLICK) in first
    # 冷却(到 ~1400)内再次捏合到阈值:第二次点击应被抑制
    second = _run(m, _hold(pinch_index, 600, 1000) + [(open_hand(), 1100)])
    assert Event(EventKind.LEFT_CLICK) not in second


def test_three_pinch_moving_up_scrolls_up():
    m = _machine()
    frames = [(open_hand(), 0)]
    for i in range(1, 11):  # 三指捻住整体上移(y 减小)
        frames.append((three_pinch(dy=-0.02 * i), i * 33))
    evs = _run(m, frames)
    scrolls = [e for e in evs if e.kind is EventKind.SCROLL]
    assert scrolls and all(e.value > 0 for e in scrolls)
    assert sum(e.value for e in scrolls) >= 3  # 累计滚动量


def test_hand_loss_during_drag_releases_button():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(pinch_index, 33, 2000)
                   + [(None, 2100)])
    assert Event(EventKind.LEFT_CLICK) in evs
    assert evs[-1] == Event(EventKind.DRAG_END)


def test_pinching_property_reflects_pinch_states():
    m = _machine()
    m.update(open_hand(), 0)
    assert m.pinching is False
    m.update(pinch_index(), 33)
    assert m.pinching is True
    m.update(open_hand(), 120)
    assert m.pinching is False


def test_disabled_gesture_emits_nothing():
    m = _machine(**{"gestures/left_click": False})
    evs = _run(m, [(open_hand(), 0)] + _hold(pinch_index, 33, 1600))
    assert evs == []


def test_hand_switch_mid_pinch_does_not_click():
    m = _machine()
    evs = _run(m, [(open_hand(), 0),
                   (pinch_index(), 33),            # 旁观者半捏合抢到选择
                   (open_hand(dx=0.4), 100),       # 切回远处操作者的张开手(瞬移)
                   (open_hand(dx=0.4), 200)])
    assert Event(EventKind.LEFT_CLICK) not in evs  # 不产生幻影点击


def test_hand_switch_mid_drag_ends_drag_once():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(pinch_index, 33, 2000)
                   + [(open_hand(dx=0.4), 2100),   # 拖拽中被另一只手抢走(瞬移)
                      (open_hand(dx=0.4), 2200)])
    assert evs.count(Event(EventKind.DRAG_END)) == 1  # 仅一次,不重复


def test_small_movement_not_treated_as_teleport():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)]
               + _hold(lambda: pinch_index(dx=0.05), 33, 1600))
    assert evs == [Event(EventKind.LEFT_CLICK), Event(EventKind.DRAG_START)]
