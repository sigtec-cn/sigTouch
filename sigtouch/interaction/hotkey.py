"""pynput GlobalHotKeys 组合串 → 人读字符串。纯 Python,便于单测。"""

_MODIFIER_NAMES = {
    "ctrl": "Ctrl", "ctrl_l": "Ctrl", "ctrl_r": "Ctrl",
    "alt": "Alt", "alt_l": "Alt", "alt_r": "Alt", "alt_gr": "Alt",
    "cmd": "Cmd", "cmd_l": "Cmd", "cmd_r": "Cmd",
    "shift": "Shift", "shift_l": "Shift", "shift_r": "Shift",
}


def _segment(raw: str) -> str:
    key = raw.strip().strip("<>").strip()
    if not key:
        return ""
    low = key.lower()
    if low in _MODIFIER_NAMES:
        return _MODIFIER_NAMES[low]
    if len(key) == 1:
        return key.upper()
    # 功能键/未知键:标题化(f1 -> F1, media_play -> Media_Play)
    return key.title()


def format_hotkey(combo: str) -> str:
    """把 "<ctrl>+<alt>+p" 转成 "Ctrl+Alt+P";空/纯空白返回 "未设置"。"""
    if not combo or not combo.strip():
        return "未设置"
    parts = [_segment(p) for p in combo.split("+")]
    parts = [p for p in parts if p]
    return "+".join(parts) if parts else "未设置"
