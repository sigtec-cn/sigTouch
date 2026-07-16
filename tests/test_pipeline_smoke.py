import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("mediapipe")


def _models_present():
    from sigtouch.perception.pipeline import MODELS_DIR
    return (MODELS_DIR / "hand_landmarker.task").exists() and \
           (MODELS_DIR / "face_landmarker.task").exists()


@pytest.mark.skipif("not _models_present()", reason="run scripts/download_models.py")
def test_black_frame_yields_no_hand_and_default_distance():
    from sigtouch.perception.pipeline import PerceptionPipeline
    p = PerceptionPipeline(frame_width=640, fov_deg=60.0)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = p.process(frame, t_ms=0)
    p.close()
    assert result.hand is None
    assert result.face_distance_m is None  # 从未见过人脸
    assert result.face_present is False
    assert result.timestamp_ms == 0
