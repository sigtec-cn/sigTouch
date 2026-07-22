"""自动检测屏幕物理尺寸(对角线英寸)。仅 macOS 有实现;检测失败返回 None。

手影物理缩放(overlay_scale)依赖真实屏幕尺寸;尺寸不准会导致影子大小失真。
CGDisplayScreenSize 读取显示硬件 EDID 的物理毫米尺寸——内建屏与多数外接屏
可读出;部分外接显示设备/投影仪不报告物理尺寸(返回 0),此时返回 None,
由上层提示用户手动填写。
"""
import logging
import math
import sys

_log = logging.getLogger(__name__)


def detect_screen_diag_inch() -> float | None:
    """返回主屏对角线英寸;无法检测返回 None。任何异常 fail-open 记日志。

    仅在真实 Cocoa 显示环境下读取;offscreen/minimal 等无屏测试平台返回 None。
    """
    if sys.platform != "darwin":
        return None
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.platformName() != "cocoa":
            return None
    except Exception:
        return None
    try:
        import ctypes
        import ctypes.util

        cg = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
        cg.CGMainDisplayID.restype = ctypes.c_uint32
        display_id = cg.CGMainDisplayID()

        class _Size(ctypes.Structure):
            _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]

        cg.CGDisplayScreenSize.restype = _Size
        size = cg.CGDisplayScreenSize(display_id)
        w_mm, h_mm = float(size.width), float(size.height)
        if w_mm <= 0 or h_mm <= 0:
            _log.info("显示硬件未报告物理尺寸,需用户手动设置")
            return None
        return round(math.hypot(w_mm, h_mm) / 25.4, 1)
    except Exception:
        _log.warning("屏幕物理尺寸检测失败", exc_info=True)
        return None
