from sigtouch.config import Config
from sigtouch.interaction.gestures import Event, EventKind, GestureStateMachine
from tests.hand_fixtures import open_hand, pinch_index, thumbs_up


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


# ---- 回车:竖大拇指保持 thumbs_up_hold_ms(默认 800) ----
def test_thumbs_up_held_fires_enter_once():
    m = _machine()
    evs = _run(m, [(open_hand(), 0)] + _hold(thumbs_up, 33, 900))
    assert evs == [Event(EventKind.ENTER)]  # 默认 800ms 触发一次


def test_thumbs_up_released_early_fires_nothing():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (thumbs_up(), 33),
                   (thumbs_up(), 400), (open_hand(), 500)])
    assert evs == []  # 不足 800ms:无回车


def test_thumbs_up_hold_time_configurable():
    m = _machine(**{"interaction/thumbs_up_hold_ms": 500})
    evs = _run(m, [(open_hand(), 0)] + _hold(thumbs_up, 33, 600))
    assert evs == [Event(EventKind.ENTER)]


def test_thumbs_up_rearms_after_release():
    m = _machine()
    hold1 = _hold(thumbs_up, 33, 900)                     # 第一次触发
    rest = [(open_hand(), 1000 + 33 * i) for i in range(1, 15)]  # 松开+过冷却
    hold2 = _hold(thumbs_up, 1600, 2500)                  # 再次触发
    evs = _run(m, [(open_hand(), 0)] + hold1 + rest + hold2)
    assert evs == [Event(EventKind.ENTER), Event(EventKind.ENTER)]


def test_thumbs_up_progress_fills_and_fires():
    m = _machine()
    m.update(open_hand(), 0)
    fracs = []
    fired = []
    for t in range(33, 900, 33):
        m.update(thumbs_up(), t)
        if m.progress is not None:
            fracs.append(m.progress.fraction)
            fired.append(m.progress.fired)
    assert fracs and max(fracs) >= 1.0
    assert True in fired  # 触发帧 fired=True


# ---- 退格:推手保持 push_hold_ms(默认 600)且面积前推 ----
def test_push_held_with_growth_fires_backspace():
    m = _machine()
    # 面积持续增大(前推),保持超过 600ms
    frames = [(open_hand(scale=1.0), 0)]
    t = 33
    scale = 1.0
    while t < 900:
        scale += 0.06
        frames.append((open_hand(scale=scale), t))
        t += 33
    evs = _run(m, frames)
    assert Event(EventKind.BACKSPACE) in evs
    assert len([e for e in evs if e.kind is EventKind.BACKSPACE]) == 1


def test_push_without_growth_does_not_fire():
    m = _machine()
    # 姿态满足但面积不增大(未前推):即使保持也不触发
    evs = _run(m, [(open_hand(scale=1.0), 0)] + _hold(lambda: open_hand(scale=1.0), 33, 900))
    assert Event(EventKind.BACKSPACE) not in evs


def test_push_released_early_fires_nothing():
    m = _machine()
    frames = [(open_hand(scale=1.0), 0), (open_hand(scale=1.2), 100),
              (open_hand(scale=1.4), 200), (open_hand(scale=1.5), 300),
              (None, 400)]  # 未到 600ms 手消失
    evs = _run(m, frames)
    assert Event(EventKind.BACKSPACE) not in evs


def test_pinch_does_not_trigger_push():
    m = _machine()
    frames = [(pinch_index(scale=1.0), 0), (pinch_index(scale=1.5), 100)]
    evs = _run(m, frames)  # 非张开手掌,推手不判定
    assert Event(EventKind.BACKSPACE) not in evs
