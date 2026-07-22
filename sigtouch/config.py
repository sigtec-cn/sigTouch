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
    "interaction/pinch_hold_ms": 1500,  # 捏合按住到该时长才触发点击(进度环)
    "interaction/thumbs_up_hold_ms": 1500,  # 竖大拇指保持该时长触发回车
    "interaction/thumbs_left_hold_ms": 1500,  # 拇指向左保持该时长触发退格
    "interaction/ok_hold_ms": 500,   # OK 手势触发回车的停留时长(已废弃,见 thumbs_up_hold_ms)
    "interaction/cooldown_ms": 400,  # 离散手势冷却
    "interaction/freeze_ms": 150,    # 捏合瞬间光标冻结时长
    "interaction/scroll_gain": 40.0, # 归一化位移→滚轮行数增益
    "interaction/active_hand": "Right",  # 控制手:"Right" | "Left"
    "interaction/smooth_min_cutoff": 1.0, # One Euro 参数
    "interaction/smooth_beta": 0.02,
    "interaction/smooth_algo": "kalman",  # 平滑算法:"kalman" | "one_euro"
    "interaction/kalman_process": 2000.0, # 卡尔曼过程噪声(大=跟手,小=稳)
    "interaction/kalman_measure": 4.0,    # 卡尔曼测量噪声(大=更平滑)
    "interaction/suspend_after_s": 3.0,   # 无人脸自动挂起时长
    "display/screen_diag_inch": 24.0,
    "display/screen_diag_detected": False,  # 屏幕尺寸是否已自动检测/用户确认;否→提示设置
    "display/overlay_opacity": 0.35,
    "display/overlay_color": "#000000",  # 深色影子默认
    "display/glow_intensity": 1.0,       # 手影亮白辉光强度(0=关闭),暗背景可读性
    "display/monitor": 0,
    "display/camera_screen_offset_m": 0.0,  # 摄像头到屏幕平面距离(米,摄像头在屏前为正)
    "display/hand_scale_multiplier": 1.0,   # 手影大小倍率(物理模型后的用户微调)
    "display/hand_max_screen_fraction": 0.25,  # 手影高度上限(占屏幕高度比例)
    "gestures/left_click": True,
    "gestures/right_click": True,
    "gestures/scroll": True,
    "gestures/enter": True,
    "gestures/backspace": True,
    "general/autostart": False,
    "general/pause_hotkey": "<ctrl>+<alt>+p",  # pynput GlobalHotKeys 语法;空串=禁用
    "general/settings_hotkey": "<ctrl>+<alt>+s",  # 唤起设置窗口的全局快捷键;空串=禁用
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
