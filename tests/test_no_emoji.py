from pathlib import Path

# UI 源码不得再含 emoji/装饰符号(lucide 图标全面替代);同时覆盖 interaction/
# 目录,防止已删除的 feedback 属性里的 "●" 之类字形借尸还魂。
_BANNED = ["📷", "✋", "🎨", "⚙️", "🖱️", "⌨️", "🔐", "🎥", "⏸", "▶", "⏻",
           "✓", "✗", "⚠️", "●", "👍"]
_ROOT = Path(__file__).resolve().parent.parent / "sigtouch"
_SCAN_DIRS = [_ROOT / "ui", _ROOT / "interaction"]


def test_ui_sources_contain_no_emoji():
    offenders = []
    for scan_dir in _SCAN_DIRS:
        for py in scan_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for ch in _BANNED:
                if ch in text:
                    offenders.append(f"{py.name}: {ch}")
    assert offenders == [], offenders
