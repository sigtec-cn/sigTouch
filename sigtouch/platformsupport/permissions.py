"""三项系统权限的检测/请求/引导。仅 macOS 需要实际检测,其余平台恒为已授权。

所有检测与请求失败一律 fail-open(视为已授权)并记录日志——权限 API 在旧系统或
特殊环境上的异常不允许影响应用可用性。
"""
import logging
import sys
from enum import Enum, auto

_log = logging.getLogger(__name__)


class PermissionKind(Enum):
    CAMERA = auto()            # 摄像头采集(视觉管线)
    ACCESSIBILITY = auto()     # pynput 鼠标/键盘注入
    INPUT_MONITORING = auto()  # pynput GlobalHotKeys 全局快捷键


_SETTINGS_URLS = {
    PermissionKind.CAMERA:
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
    PermissionKind.ACCESSIBILITY:
        "x-apple.systempreferences:com.apple.preference.security"
        "?Privacy_Accessibility",
    PermissionKind.INPUT_MONITORING:
        "x-apple.systempreferences:com.apple.preference.security"
        "?Privacy_ListenEvent",
}

_AV_AUTHORIZED = 3            # AVAuthorizationStatusAuthorized
_HID_REQUEST_LISTEN = 1       # kIOHIDRequestTypeListenEvent
_HID_ACCESS_GRANTED = 0       # kIOHIDAccessTypeGranted(1=denied, 2=unknown→未授权)


def check(kind: PermissionKind) -> bool:
    if sys.platform != "darwin":
        return True
    try:
        if kind is PermissionKind.CAMERA:
            return _camera_status_darwin()
        if kind is PermissionKind.ACCESSIBILITY:
            return _accessibility_trusted_darwin(prompt=False)
        return _input_monitoring_status_darwin()
    except Exception:
        _log.warning("权限检测失败,按已授权处理: %s", kind, exc_info=True)
        return True


def request(kind: PermissionKind) -> None:
    """触发系统授权弹窗。非 macOS no-op;失败仅记录。"""
    if sys.platform != "darwin":
        return
    try:
        if kind is PermissionKind.CAMERA:
            _camera_request_darwin()
        elif kind is PermissionKind.ACCESSIBILITY:
            _accessibility_trusted_darwin(prompt=True)
        else:
            _input_monitoring_request_darwin()
    except Exception:
        _log.warning("权限请求失败: %s", kind, exc_info=True)


def open_settings(kind: PermissionKind) -> None:
    """打开系统设置中对应的隐私面板。非 macOS no-op。"""
    if sys.platform != "darwin":
        return
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(_SETTINGS_URLS[kind]))
    except Exception:
        _log.warning("打开系统设置失败: %s", kind, exc_info=True)


def snapshot() -> dict[PermissionKind, bool]:
    return {kind: check(kind) for kind in PermissionKind}


def all_granted() -> bool:
    return all(snapshot().values())


# ---- macOS 实现(懒导入;仅在 darwin 分支到达) ----

def _camera_status_darwin() -> bool:
    from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeVideo)
    return status == _AV_AUTHORIZED  # NotDetermined/Denied 都视为未授权以便引导


def _camera_request_darwin() -> None:
    from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
    AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        AVMediaTypeVideo, lambda granted: None)


def _accessibility_trusted_darwin(prompt: bool) -> bool:
    from ApplicationServices import (AXIsProcessTrusted,
                                     AXIsProcessTrustedWithOptions,
                                     kAXTrustedCheckOptionPrompt)
    if prompt:
        return bool(AXIsProcessTrustedWithOptions(
            {kAXTrustedCheckOptionPrompt: True}))
    return bool(AXIsProcessTrusted())


def _iokit():
    import ctypes
    import ctypes.util
    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
    return lib, ctypes


def _input_monitoring_status_darwin() -> bool:
    lib, ctypes = _iokit()
    lib.IOHIDCheckAccess.restype = ctypes.c_int
    lib.IOHIDCheckAccess.argtypes = [ctypes.c_int]
    return lib.IOHIDCheckAccess(_HID_REQUEST_LISTEN) == _HID_ACCESS_GRANTED


def _input_monitoring_request_darwin() -> None:
    lib, ctypes = _iokit()
    lib.IOHIDRequestAccess.restype = ctypes.c_bool
    lib.IOHIDRequestAccess.argtypes = [ctypes.c_int]
    lib.IOHIDRequestAccess(_HID_REQUEST_LISTEN)


# Task 3 移除:app.py 迁移到 check() 前的兼容 shim
def accessibility_ok() -> bool:
    return check(PermissionKind.ACCESSIBILITY)
