from sigtouch.interaction.gestures import Event, EventKind
from sigtouch.output.injector import Injector


class FakeMouse:
    def __init__(self):
        self.position = (0, 0)
        self.calls = []

    def click(self, button, count=1):
        self.calls.append(("click", str(button), count))

    def press(self, button):
        self.calls.append(("press", str(button)))

    def release(self, button):
        self.calls.append(("release", str(button)))

    def scroll(self, dx, dy):
        self.calls.append(("scroll", dx, dy))


class FakeKeyboard:
    def __init__(self):
        self.taps = []

    def tap(self, key):
        self.taps.append(str(key))


def _injector():
    m, k = FakeMouse(), FakeKeyboard()
    return Injector(mouse=m, keyboard=k), m, k


def test_move_sets_position():
    inj, m, _ = _injector()
    inj.move(100, 200)
    assert m.position == (100, 200)


def test_dispatch_clicks_and_drag():
    inj, m, _ = _injector()
    inj.dispatch(Event(EventKind.LEFT_CLICK))
    inj.dispatch(Event(EventKind.RIGHT_CLICK))
    inj.dispatch(Event(EventKind.DRAG_START))
    inj.dispatch(Event(EventKind.DRAG_END))
    kinds = [c[0] for c in m.calls]
    assert kinds == ["click", "click", "press", "release"]


def test_dispatch_scroll_passes_lines():
    inj, m, _ = _injector()
    inj.dispatch(Event(EventKind.SCROLL, value=3.0))
    assert m.calls == [("scroll", 0, 3)]


def test_dispatch_keys():
    inj, _, k = _injector()
    inj.dispatch(Event(EventKind.ENTER))
    inj.dispatch(Event(EventKind.BACKSPACE))
    assert len(k.taps) == 2


def test_release_all_releases_left_only_if_dragging():
    inj, m, _ = _injector()
    inj.release_all()
    assert m.calls == []          # 未拖拽,无动作
    inj.dispatch(Event(EventKind.DRAG_START))
    inj.release_all()
    assert m.calls[-1][0] == "release"
