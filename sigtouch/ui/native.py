# sigtouch/ui/native.py
"""平台原生窗口增强。非 macOS 一律 no-op;任何失败 fail-open 仅记日志。"""
import logging
import sys

_log = logging.getLogger(__name__)

# NSWindowCollectionBehavior 位标志
_CAN_JOIN_ALL_SPACES = 1 << 0
_STATIONARY = 1 << 4
_FULLSCREEN_AUXILIARY = 1 << 8
_SCREEN_SAVER_LEVEL = 1000  # NSScreenSaverWindowLevel:高于全屏窗口层


def pin_window_topmost(widget) -> None:
    """把 Qt 窗口提升到所有窗口(含全屏 App)之上并跟随所有空间。仅 macOS 有实际动作。"""
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtGui import QGuiApplication

        # winId() 只有在真正的 Cocoa QPA 插件下才是有效 NSView 指针;
        # offscreen/minimal 等测试用平台会返回占位句柄,直接喂给 objc 桥接
        # 会解引用野指针导致 segfault(Python 异常捕获不到原生崩溃),
        # 因此在进入 objc 桥接前先确认当前确实跑在 cocoa 平台上。
        if QGuiApplication.platformName() != "cocoa":
            return

        import objc  # pyobjc-framework-Cocoa
        from ctypes import c_void_p

        ns_view = objc.objc_object(c_void_p=c_void_p(int(widget.winId())))
        ns_window = ns_view.window()
        if ns_window is None:
            return
        ns_window.setLevel_(_SCREEN_SAVER_LEVEL)
        ns_window.setCollectionBehavior_(
            _CAN_JOIN_ALL_SPACES | _STATIONARY | _FULLSCREEN_AUXILIARY)
    except Exception:
        _log.warning("原生置顶设置失败,回退 Qt 置顶", exc_info=True)
