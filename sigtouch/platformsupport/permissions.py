"""macOS 辅助功能权限检测(输入注入必需)。检测失败不阻塞启动。"""
import sys


def accessibility_ok() -> bool:
    if sys.platform != "darwin":
        return True
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.cdll.LoadLibrary(
            ctypes.util.find_library("ApplicationServices"))
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True
