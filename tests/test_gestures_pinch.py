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


def test_quick_pinch_release_is_left_click():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (pinch_index(), 33), (pinch_index(), 100),
                   (open_hand(), 200)])
    assert evs == [Event(EventKind.LEFT_CLICK)]


def test_held_pinch_is_drag_not_click():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (pinch_index(), 33), (pinch_index(), 150),
                   (pinch_index(), 320), (pinch_index(), 400), (open_hand(), 500)])
    assert evs == [Event(EventKind.DRAG_START), Event(EventKind.DRAG_END)]


def test_quick_middle_pinch_is_right_click():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (pinch_middle(), 33), (open_hand(), 150)])
    assert evs == [Event(EventKind.RIGHT_CLICK)]


def test_held_middle_pinch_does_nothing():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (pinch_middle(), 33), (pinch_middle(), 400),
                   (open_hand(), 500)])
    assert evs == []


def test_cooldown_suppresses_rapid_second_click():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (pinch_index(), 33), (open_hand(), 120),
                   (pinch_index(), 200), (open_hand(), 300),   # 冷却内,吞掉
                   (pinch_index(), 700), (open_hand(), 800)])  # 冷却后
    assert evs == [Event(EventKind.LEFT_CLICK), Event(EventKind.LEFT_CLICK)]


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
    evs = _run(m, [(open_hand(), 0), (pinch_index(), 33), (pinch_index(), 320),
                   (None, 400)])
    assert evs == [Event(EventKind.DRAG_START), Event(EventKind.DRAG_END)]


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
    evs = _run(m, [(open_hand(), 0), (pinch_index(), 33), (open_hand(), 120)])
    assert evs == []
