import pytest

from sigtouch.config import Config
from sigtouch.interaction import features as F
from sigtouch.interaction.gestures import EventKind, GestureStateMachine
from tests.hand_fixtures import open_hand, thumbs_left, thumbs_left_up_diagonal, thumbs_up


def _machine():
    return GestureStateMachine(Config(backend={}))


def _run(m, frames):
    out = []
    for hand, t in frames:
        out.extend(m.update(hand, t))
    return out


def test_is_thumbs_left_detects_left_pointing_thumb():
    assert F.is_thumbs_left(thumbs_left()) is True
    assert F.is_thumbs_left(open_hand()) is False
    assert F.is_thumbs_left(thumbs_up()) is False          # 与竖拇指互斥


def test_is_thumbs_left_hand_agnostic():
    assert F.is_thumbs_left(thumbs_left(handedness="Left")) is True


def test_thumbs_up_not_confused_with_left():
    assert F.is_thumbs_up(thumbs_left()) is False


def test_hold_1500ms_fires_backspace_once():
    m = _machine()
    frames = [(open_hand(), 0)] + \
             [(thumbs_left(), 33 * i) for i in range(1, 70)]  # 持续到 ~2.3s
    evs = _run(m, frames)
    assert [e.kind for e in evs] == [EventKind.BACKSPACE]


def test_early_release_no_backspace():
    m = _machine()
    evs = _run(m, [(open_hand(), 0), (thumbs_left(), 33),
                   (thumbs_left(), 800), (open_hand(), 900)])  # 不足 1500ms
    assert evs == []


def test_backspace_progress_reported():
    m = _machine()
    m.update(open_hand(), 0)
    m.update(thumbs_left(), 33)
    m.update(thumbs_left(), 780)     # ~50%
    p = m.progress
    assert p is not None and p.kind == "backspace"
    assert 0.3 < p.fraction < 0.7


def test_thumbs_left_hold_survives_thumb_drifting_up():
    from tests.hand_fixtures import thumbs_left, thumbs_left_up_diagonal
    m = _machine()
    # 纯左起手,中途拇指略上飘(两谓词都满足),再回纯左 —— 保持不被踢,恰触发一次退格
    frames = [(open_hand(), 0)]
    for i in range(1, 70):
        t = 33 * i
        hand = thumbs_left_up_diagonal() if 20 <= i <= 30 else thumbs_left()
        frames.append((hand, t))
    evs = _run(m, frames)
    assert [e.kind for e in evs] == [EventKind.BACKSPACE]   # 未因漂移重置计时


def test_push_keys_removed_from_defaults():
    cfg = Config(backend={})
    for key in ("interaction/push_hold_ms", "interaction/push_area_ratio",
                "interaction/push_window_ms"):
        with pytest.raises(KeyError):
            cfg.get(key)
    assert cfg.get("interaction/thumbs_left_hold_ms") == 1500
    assert cfg.get("interaction/thumbs_up_hold_ms") == 1500
