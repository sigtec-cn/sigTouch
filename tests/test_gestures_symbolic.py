from sigtouch.config import Config
from sigtouch.interaction.gestures import Event, EventKind, GestureStateMachine
from tests.hand_fixtures import open_hand, pinch_index, thumbs_left, thumbs_up


def _machine(**overrides):
    cfg = Config(backend={})
    for k, v in overrides.items():
        cfg.set(k, v)
    return GestureStateMachine(cfg)


def _run(m, frames):
    out = []
    for hand, t in frames:
        out.extend(m.update(hand, t))
    return out


def _hold(hand_fn, start_ms, end_ms, step=33):
    return [(hand_fn(), t) for t in range(start_ms, end_ms, step)]


# ---- 回车:竖大拇指保持 thumbs_up_hold_ms(默认 1500) ----
def test_thumbs_up_held_fires_enter_once():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(thumbs_up, 33, 1600))
    assert evs == [Event(EventKind.ENTER)]  # 默认 1500ms 触发一次


def test_thumbs_up_released_early_fires_nothing():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (thumbs_up(), 33),
                   (thumbs_up(), 400), (open_hand(), 500)])
    assert evs == []  # 不足 1500ms:无回车


def test_thumbs_up_hold_time_configurable():
    m = _machine(**{"interaction/thumbs_up_hold_ms": 500})
    evs = _run(m, [(open_hand(), 0)] + _hold(thumbs_up, 33, 600))
    assert evs == [Event(EventKind.ENTER)]


def test_thumbs_up_rearms_after_release():
    m = _machine()
    hold1 = _hold(thumbs_up, 33, 1600)                    # 第一次触发(默认 1500ms)
    rest = [(open_hand(), 1600 + 33 * i) for i in range(1, 15)]  # 松开+过冷却
    hold2 = _hold(thumbs_up, 2200, 3800)                  # 再次触发
    evs = _run(m, [(open_hand(), 0)] + hold1 + rest + hold2)
    assert evs == [Event(EventKind.ENTER), Event(EventKind.ENTER)]


def test_thumbs_up_progress_fills_and_fires():
    m = _machine()
    m.update(open_hand(), 0)
    fracs = []
    fired = []
    for t in range(33, 1700, 33):
        m.update(thumbs_up(), t)
        if m.progress is not None:
            fracs.append(m.progress.fraction)
            fired.append(m.progress.fired)
    assert fracs and max(fracs) >= 1.0
    assert True in fired  # 触发帧 fired=True


# ---- 退格:拇指向左保持 thumbs_left_hold_ms(默认 1500) ----
def test_thumbs_left_held_fires_backspace_once():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(thumbs_left, 33, 1600))
    assert evs == [Event(EventKind.BACKSPACE)]  # 默认 1500ms 触发一次


def test_thumbs_left_released_early_fires_nothing():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (thumbs_left(), 33),
                   (thumbs_left(), 800), (open_hand(), 900)])
    assert evs == []  # 不足 1500ms:无退格


def test_thumbs_left_hold_time_configurable():
    m = _machine(**{"interaction/thumbs_left_hold_ms": 500})
    evs = _run(m, [(open_hand(), 0)] + _hold(thumbs_left, 33, 600))
    assert evs == [Event(EventKind.BACKSPACE)]


def test_thumbs_left_rearms_after_release():
    m = _machine()
    hold1 = _hold(thumbs_left, 33, 1600)                  # 第一次触发(默认 1500ms)
    rest = [(open_hand(), 1600 + 33 * i) for i in range(1, 15)]  # 松开+过冷却
    hold2 = _hold(thumbs_left, 2200, 3800)                # 再次触发
    evs = _run(m, [(open_hand(), 0)] + hold1 + rest + hold2)
    assert evs == [Event(EventKind.BACKSPACE), Event(EventKind.BACKSPACE)]


def test_pinch_does_not_trigger_backspace():
    m = _machine()
    frames = [(pinch_index(scale=1.0), 0), (pinch_index(scale=1.5), 100)]
    evs = _run(m, frames)  # 捏合姿态,非拇指向左,不触发退格
    assert Event(EventKind.BACKSPACE) not in evs
