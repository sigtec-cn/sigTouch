from sigtouch.interaction.mapper import CursorMapper


def _drive(m, anchor, t0=0, n=30, dt=33, pinching=False):
    """喂同一锚点多帧让滤波收敛,返回最后输出。"""
    out = None
    for i in range(n):
        out = m.update(anchor, pinching, t0 + i * dt)
    return out


def test_center_maps_to_screen_center():
    m = CursorMapper(1920, 1080, margin=0.15)
    assert _drive(m, (0.5, 0.5)) == (960, 540)


def test_interaction_box_edges_map_to_screen_edges():
    m = CursorMapper(1920, 1080, margin=0.15)
    assert _drive(m, (0.15, 0.15)) == (0, 0)
    m2 = CursorMapper(1920, 1080, margin=0.15)
    assert _drive(m2, (0.85, 0.85)) == (1919, 1079)


def test_outside_box_clamps():
    m = CursorMapper(1920, 1080, margin=0.15)
    assert _drive(m, (0.05, 0.99)) == (0, 1079)


def test_pinch_freezes_cursor_then_resumes():
    m = CursorMapper(1920, 1080, margin=0.15, freeze_ms=150)
    _drive(m, (0.5, 0.5), t0=0, n=30)          # 稳定在中心, t 到 ~957
    frozen = m.update((0.7, 0.5), True, 1000)   # 捏合瞬间手滑了
    assert frozen == (960, 540)                 # 冻结:仍是捏合前位置
    still = m.update((0.7, 0.5), True, 1100)    # 冻结期内
    assert still == (960, 540)
    moved = m.update((0.7, 0.5), True, 1200)    # 冻结结束(>1000+150)
    assert moved[0] > 960                       # 恢复跟随
