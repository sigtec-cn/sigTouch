import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("cv2")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _thread(qapp):
    from sigtouch.config import Config
    from sigtouch.vision import VisionThread
    return VisionThread(Config(backend={}))


def test_interruptible_sleep_waits_when_running(qapp):
    t = _thread(qapp)
    start = time.monotonic()
    t._interruptible_sleep(0.3)
    assert time.monotonic() - start >= 0.28


def test_interruptible_sleep_exits_fast_when_stopped(qapp):
    t = _thread(qapp)
    t._running = False
    start = time.monotonic()
    t._interruptible_sleep(5.0)
    assert time.monotonic() - start < 0.2
