from pathlib import Path

# UI 源码不得再含 emoji/装饰符号(lucide 图标全面替代)
_BANNED = ["📷", "✋", "🎨", "⚙️", "🖱️", "⌨️", "🔐", "🎥", "⏸", "▶", "⏻",
           "✓", "✗", "⚠️", "●", "👍"]
_UI_DIR = Path(__file__).resolve().parent.parent / "sigtouch" / "ui"


def test_ui_sources_contain_no_emoji():
    offenders = []
    for py in _UI_DIR.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for ch in _BANNED:
            if ch in text:
                offenders.append(f"{py.name}: {ch}")
    assert offenders == [], offenders
