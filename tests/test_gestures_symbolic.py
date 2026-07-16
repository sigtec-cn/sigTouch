from sigtouch.config import Config
from sigtouch.interaction.gestures import Event, EventKind, GestureStateMachine
from tests.hand_fixtures import ok_pose, open_hand, pinch_index


def _machine():
    return GestureStateMachine(Config(backend={}))


def _run(m, frames):
    out = []
    for hand, t in frames:
        out.extend(m.update(hand, t))
    return out


def test_ok_held_500ms_fires_enter_once():
    m = _machine()
    frames = [(open_hand(), 0)] + \
             [(ok_pose(), 33 * i) for i in range(1, 30)]  # 持续到 ~957ms
    evs = _run(m, frames)
    assert evs == [Event(EventKind.ENTER)]  # 只触发一次,不重复


def test_ok_released_early_fires_nothing():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (ok_pose(), 33), (ok_pose(), 200),
                   (open_hand(), 300)])
    assert evs == []  # 不足 500ms:无回车,也不误报左键


def test_ok_rearms_after_release():
    m = _machine()
    hold1 = [(ok_pose(), 33 * i) for i in range(1, 20)]          # 第一次触发
    rest = [(open_hand(), 700 + 33 * i) for i in range(1, 10)]   # 松开+过冷却
    hold2 = [(ok_pose(), 1100 + 33 * i) for i in range(1, 20)]   # 再次触发
    evs = _run(m, [(open_hand(), 0)] + hold1 + rest + hold2)
    assert evs == [Event(EventKind.ENTER), Event(EventKind.ENTER)]


def test_feedback_set_on_enter_frame():
    m = _machine()
    m.update(open_hand(), 0)
    feedbacks = []
    for i in range(1, 30):
        m.update(ok_pose(), 33 * i)
        feedbacks.append(m.feedback)
    assert "⏎" in feedbacks
    assert feedbacks[-1] is None  # 触发帧之后清空


def test_palm_push_fires_backspace():
    m = _machine()
    frames = [(open_hand(scale=1.0), 0), (open_hand(scale=1.0), 33),
              (open_hand(scale=1.1), 66), (open_hand(scale=1.25), 99),
              (open_hand(scale=1.45), 132)]  # 300ms 窗口内面积增大 >1.35²... 实际按比值
    evs = _run(m, frames)
    assert Event(EventKind.BACKSPACE) in evs
    assert len([e for e in evs if e.kind is EventKind.BACKSPACE]) == 1


def test_slow_growth_does_not_fire_backspace():
    m = _machine()
    frames = [(open_hand(scale=1.0 + 0.02 * i), 400 * i) for i in range(10)]
    evs = _run(m, frames)  # 每帧间隔 400ms > 窗口,永远只有一个样本参与比较
    assert evs == []


def test_pinch_does_not_trigger_push():
    m = _machine()
    frames = [(pinch_index(scale=1.0), 0), (pinch_index(scale=1.5), 100)]
    evs = _run(m, frames)  # 非张开手掌,推手不判定
    assert Event(EventKind.BACKSPACE) not in evs
