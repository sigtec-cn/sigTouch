"""配置默认值与读写。backend 为任意 MutableMapping:测试用 dict,应用用 QSettings 适配器。"""
from typing import Any

DEFAULTS: dict[str, Any] = {
    "camera/index": 0,
    "camera/width": 640,
    "camera/height": 480,
    "camera/fov_deg": 60.0,          # 水平视场角,距离估计用
    "interaction/box_margin": 0.15,  # 交互框四边留白比例
    "interaction/pinch_enter": 0.35, # 捏合进入阈值(指尖距/手掌尺寸)
    "interaction/pinch_exit": 0.55,  # 捏合退出阈值(滞回)
    "interaction/click_max_ms": 250, # 快捻=点击的最长保持时间
    "interaction/ok_hold_ms": 500,   # OK 手势触发回车的停留时长
    "interaction/cooldown_ms": 400,  # 离散手势冷却
    "interaction/freeze_ms": 150,    # 捏合瞬间光标冻结时长
    "interaction/scroll_gain": 40.0, # 归一化位移→滚轮行数增益
    "interaction/active_hand": "Right",  # 控制手:"Right" | "Left"
    "interaction/push_area_ratio": 1.35,  # 推手:包围盒面积放大倍数
    "interaction/push_window_ms": 300,    # 推手:面积增长观察窗口
    "interaction/smooth_min_cutoff": 1.0, # One Euro 参数
    "interaction/smooth_beta": 0.02,
    "interaction/suspend_after_s": 3.0,   # 无人脸自动挂起时长
    "display/screen_diag_inch": 24.0,
    "display/overlay_opacity": 0.35,
    "display/overlay_color": "#000000",  # 深色影子默认
    "display/monitor": 0,
    "gestures/left_click": True,
    "gestures/right_click": True,
    "gestures/scroll": True,
    "gestures/enter": True,
    "gestures/backspace": True,
    "general/autostart": False,
    "general/pause_hotkey": "<ctrl>+<alt>+p",  # pynput GlobalHotKeys 语法;空串=禁用
}

_FALSY_STRINGS = {"false", "0", "no", "off", ""}


class Config:
    def __init__(self, backend=None):
        self._backend = backend if backend is not None else {}

    def get(self, key: str) -> Any:
        if key not in DEFAULTS:
            raise KeyError(key)
        raw = self._backend.get(key)
        if raw is None:
            return DEFAULTS[key]
        default = DEFAULTS[key]
        if isinstance(default, bool):
            if isinstance(raw, str):
                return raw.strip().lower() not in _FALSY_STRINGS
            return bool(raw)
        return type(default)(raw)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        self._backend[key] = value
