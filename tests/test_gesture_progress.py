# tests/test_gesture_progress.py — 结构化进度暴露(供 overlay 渲染)
from sigtouch.config import Config
from sigtouch.interaction.gestures import GestureStateMachine
from tests.hand_fixtures import open_hand, pinch_index, thumbs_left, thumbs_up


def _machine(**overrides):
    cfg = Config(backend={})
    for k, v in overrides.items():
        cfg.set(k, v)
    return GestureStateMachine(cfg)


def _hold(hand_fn, start_ms, end_ms, step=33):
    return [(hand_fn(), t) for t in range(start_ms, end_ms, step)]


def test_left_click_progress_fraction_grows_to_fire():
    m = _machine(**{"interaction/pinch_hold_ms": 900})
    m.update(open_hand(), 0)
    fracs = []
    fired = []
    for t in range(33, 1000, 33):
        m.update(pinch_index(), t)
        if m.progress is not None:
            assert m.progress.kind == "left_click"
            fracs.append(m.progress.fraction)
            fired.append(m.progress.fired)
    assert fracs and fracs[0] < 1.0          # 早期未满
    assert True in fired                      # 触发帧 fired=True
    # fraction 单调不减(允许平台)
    assert all(b >= a - 1e-6 for a, b in zip(fracs, fracs[1:]))


def test_progress_none_when_no_gesture():
    m = _machine()
    m.update(open_hand(), 0)
    m.update(open_hand(), 33)
    assert m.progress is None  # 张开手(非捏合/非竖拇指/非拇指向左)→ 无进度


def test_enter_progress_kind_and_fire():
    m = _machine(**{"interaction/thumbs_up_hold_ms": 500})
    m.update(open_hand(), 0)
    seen_fire = False
    for t in range(33, 700, 33):
        m.update(thumbs_up(), t)
        if m.progress is not None:
            assert m.progress.kind == "enter"
            if m.progress.fired:
                seen_fire = True
    assert seen_fire


def test_progress_fraction_clamped_to_one():
    m = _machine(**{"interaction/pinch_hold_ms": 500})
    m.update(open_hand(), 0)
    for t in range(33, 800, 33):
        m.update(pinch_index(), t)
        if m.progress is not None:
            assert 0.0 <= m.progress.fraction <= 1.0


def test_backspace_progress_kind():
    m = _machine()
    # 拇指向左保持中 → 进入 THUMBS_LEFT
    m.update(open_hand(), 0)
    m.update(thumbs_left(), 33)
    m.update(thumbs_left(), 66)
    if m.progress is not None:
        assert m.progress.kind == "backspace"
