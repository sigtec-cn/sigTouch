# sigtouch/ui/native.py
"""平台原生窗口增强。非 macOS 一律 no-op;任何失败 fail-open 仅记日志。"""
import logging
import sys

_log = logging.getLogger(__name__)

# NSWindowCollectionBehavior 位标志
_CAN_JOIN_ALL_SPACES = 1 << 0
_STATIONARY = 1 << 4
_FULLSCREEN_AUXILIARY = 1 << 8
_NORMAL_LEVEL = 0  # NSNormalWindowLevel
_SCREEN_SAVER_LEVEL = 1000  # NSScreenSaverWindowLevel:高于全屏窗口层

# NSApplicationActivationPolicy
_ACTIVATION_REGULAR = 0    # 普通 App:有 Dock 图标、可获键盘焦点
_ACTIVATION_ACCESSORY = 1  # Agent/托盘 App:无 Dock 图标、默认不激活


def set_activation_policy_regular() -> None:
    """临时切为 Regular:LSUIElement 托盘 App 弹配置窗前调用,窗口才能置前获焦。

    macOS 对 accessory 应用不激活、不给键盘焦点,从托盘菜单弹出的窗口会
    被压在其他窗口下且不响应输入,看起来像"没有配置 UI"。切为 Regular 后
    出现 Dock 图标并可正常交互;窗口关完应调 set_activation_policy_accessory()
    恢复纯托盘。仅 macOS 有实际动作,失败 fail-open。
    """
    _set_activation_policy(_ACTIVATION_REGULAR)


def set_activation_policy_accessory() -> None:
    """恢复 Accessory 纯托盘(与 set_activation_policy_regular 对称)。仅 macOS。"""
    _set_activation_policy(_ACTIVATION_ACCESSORY)


def activate_app() -> None:
    """把本 App 拉到前台(配合 Regular 策略,让弹窗立即获得焦点)。仅 macOS。"""
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.platformName() != "cocoa":
            return
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular

        ns_app = NSApplication.sharedApplication()
        ns_app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        # activateIgnoringOtherApps 在 macOS 14 已废弃,但仍是把托盘 App
        # 弹窗拉到前台最可靠的途径;activate 需要应用已是 active 才生效。
        ns_app.activateIgnoringOtherApps_(True)
    except Exception:
        _log.warning("激活本 App 到前台失败,窗口可能不置前", exc_info=True)


def _set_activation_policy(policy: int) -> None:
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtGui import QGuiApplication

        if QGuiApplication.platformName() != "cocoa":
            return
        from AppKit import NSApplication

        NSApplication.sharedApplication().setActivationPolicy_(policy)
    except Exception:
        _log.warning("设置激活策略失败", exc_info=True)


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


def unpin_window_topmost(widget) -> None:
    """把窗口降回普通层级(与 pin_window_topmost 对称)。仅 macOS 有实际动作。"""
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
        ns_window.setLevel_(_NORMAL_LEVEL)
        ns_window.setCollectionBehavior_(0)
    except Exception:
        _log.warning("恢复普通窗口层级失败,保持当前层级", exc_info=True)
