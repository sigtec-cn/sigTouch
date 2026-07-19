from sigtouch.interaction.hotkey import format_hotkey


def test_ctrl_alt_p():
    assert format_hotkey("<ctrl>+<alt>+p") == "Ctrl+Alt+P"


def test_cmd_shift_s():
    assert format_hotkey("<cmd>+<shift>+s") == "Cmd+Shift+S"


def test_single_function_key():
    assert format_hotkey("<f1>") == "F1"


def test_modifier_side_aliases_normalized():
    assert format_hotkey("<ctrl_l>+a") == "Ctrl+A"


def test_empty_or_blank_is_unset():
    assert format_hotkey("") == "未设置"
    assert format_hotkey("   ") == "未设置"


def test_plain_letter():
    assert format_hotkey("a") == "A"


def test_unknown_segment_titlecased():
    assert format_hotkey("<ctrl>+<media_play>") == "Ctrl+Media_Play"
