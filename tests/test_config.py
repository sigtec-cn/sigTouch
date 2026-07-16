import pytest
from sigtouch.config import Config, DEFAULTS


def test_get_returns_default_when_unset():
    cfg = Config(backend={})
    assert cfg.get("camera/index") == 0
    assert cfg.get("interaction/pinch_enter") == pytest.approx(0.35)
    assert cfg.get("display/screen_diag_inch") == pytest.approx(24.0)
    assert cfg.get("gestures/left_click") is True


def test_set_then_get_roundtrip():
    cfg = Config(backend={})
    cfg.set("camera/index", 2)
    assert cfg.get("camera/index") == 2


def test_get_coerces_string_values_from_backend():
    # QSettings 在部分平台把值存成字符串,get 必须按默认值类型转换回来
    cfg = Config(backend={"camera/fov_deg": "72.5", "gestures/enter": "false",
                          "camera/width": "1280"})
    assert cfg.get("camera/fov_deg") == pytest.approx(72.5)
    assert cfg.get("gestures/enter") is False
    assert cfg.get("camera/width") == 1280


def test_unknown_key_raises():
    cfg = Config(backend={})
    with pytest.raises(KeyError):
        cfg.get("nope/nothing")
    with pytest.raises(KeyError):
        cfg.set("nope/nothing", 1)


def test_defaults_cover_all_sections():
    sections = {k.split("/")[0] for k in DEFAULTS}
    assert sections == {"camera", "interaction", "display", "gestures", "general"}
