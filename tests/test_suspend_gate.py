from sigtouch.app import SuspendGate


def test_suspended_until_first_face():
    g = SuspendGate(suspend_after_ms=3000)
    assert g.update(False, 0) is True      # 从未见过人脸 → 挂起


def test_active_while_face_present_and_within_grace():
    g = SuspendGate(suspend_after_ms=3000)
    assert g.update(True, 0) is False
    assert g.update(False, 1000) is False   # 3 秒宽限期内
    assert g.update(False, 2999) is False


def test_suspends_after_grace_and_recovers():
    g = SuspendGate(suspend_after_ms=3000)
    g.update(True, 0)
    assert g.update(False, 3001) is True
    assert g.update(True, 4000) is False    # 人回来立即恢复
