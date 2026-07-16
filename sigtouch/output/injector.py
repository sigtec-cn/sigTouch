"""把手势事件翻译成系统输入。pynput 懒加载,测试注入假控制器。"""
from sigtouch.interaction.gestures import Event, EventKind

# Try to import pynput symbols; fallback with dummy objects for testing/headless
try:
    from pynput.keyboard import Key
    from pynput.mouse import Button
except (ImportError, Exception):
    # Fallback for testing environments or headless systems without pynput
    class _FakeKey:
        enter = "Key.enter"
        backspace = "Key.backspace"

    class _FakeButton:
        left = "Button.left"
        right = "Button.right"

    Key = _FakeKey()
    Button = _FakeButton()


class Injector:
    def __init__(self, mouse=None, keyboard=None):
        if mouse is None or keyboard is None:
            from pynput.keyboard import Controller as KeyboardController
            from pynput.mouse import Controller as MouseController

            mouse = mouse or MouseController()
            keyboard = keyboard or KeyboardController()
        self._mouse = mouse
        self._kb = keyboard
        self._dragging = False

    def move(self, x: int, y: int) -> None:
        self._mouse.position = (x, y)

    def dispatch(self, ev: Event) -> None:
        k = ev.kind
        if k is EventKind.LEFT_CLICK:
            self._mouse.click(Button.left, 1)
        elif k is EventKind.RIGHT_CLICK:
            self._mouse.click(Button.right, 1)
        elif k is EventKind.DRAG_START:
            self._mouse.press(Button.left)
            self._dragging = True
        elif k is EventKind.DRAG_END:
            self._mouse.release(Button.left)
            self._dragging = False
        elif k is EventKind.SCROLL:
            self._mouse.scroll(0, int(ev.value))
        elif k is EventKind.ENTER:
            self._kb.tap(Key.enter)
        elif k is EventKind.BACKSPACE:
            self._kb.tap(Key.backspace)

    def release_all(self) -> None:
        """暂停/挂起/退出时调用,防止左键卡在按下状态。"""
        if self._dragging:
            self._mouse.release(Button.left)
            self._dragging = False
