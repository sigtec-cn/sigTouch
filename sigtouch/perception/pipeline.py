# sigtouch/perception/pipeline.py
"""MediaPipe Tasks 封装:手部 21 点 + 人脸虹膜 → FrameResult。仅在视觉线程使用。"""
import math
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (FaceLandmarker, FaceLandmarkerOptions,
                                           HandLandmarker, HandLandmarkerOptions,
                                           RunningMode)

from sigtouch.perception.distance import (DistanceSmoother, estimate_distance_m,
                                          focal_px)
from sigtouch.perception.types import FrameResult, HandFrame

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
# FaceLandmarker 478 点模型的虹膜中心索引
_RIGHT_IRIS_CENTER = 468
_LEFT_IRIS_CENTER = 473


def select_hand(hands, wanted):
    """按 handedness 过滤后取手掌尺寸最大者(最近的人的手);无匹配返回 None。

    掌尺寸 = 腕(0)到中指根(9)的归一化距离,与 features.palm_size 同定义。
    """
    best = None
    best_size = -1.0
    for label, lms in hands:
        if label != wanted:
            continue
        size = math.dist(lms[0][:2], lms[9][:2])
        if size > best_size:
            best, best_size = lms, size
    return best


def select_primary_face(faces):
    """取瞳距像素最大(离摄像头最近)的脸;空列表返回 None。"""
    best = None
    best_span = -1.0
    for f in faces:
        r, l = f[_RIGHT_IRIS_CENTER], f[_LEFT_IRIS_CENTER]
        span = math.hypot(r.x - l.x, r.y - l.y)
        if span > best_span:
            best, best_span = f, span
    return best


class PerceptionPipeline:
    def __init__(self, frame_width: int, fov_deg: float,
                 models_dir: Path | None = None, active_hand: str = "Right"):
        d = models_dir or MODELS_DIR
        self._active_hand = active_hand
        self._hands = HandLandmarker.create_from_options(HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(d / "hand_landmarker.task")),
            running_mode=RunningMode.VIDEO, num_hands=4))
        self._face = FaceLandmarker.create_from_options(FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(d / "face_landmarker.task")),
            running_mode=RunningMode.VIDEO, num_faces=3))
        self._focal = focal_px(frame_width, fov_deg)
        self._smoother = DistanceSmoother()
        self._seen_face = False  # 历史上是否见过人脸(未见过时距离返回 None 而非默认值)

    def process(self, bgr_frame, t_ms: int) -> FrameResult:
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        h_px, w_px = bgr_frame.shape[:2]

        hand = None
        hres = self._hands.detect_for_video(image, t_ms)
        if hres.hand_landmarks:
            candidates = [
                (hres.handedness[i][0].category_name,
                 [(p.x, p.y, p.z) for p in lms])
                for i, lms in enumerate(hres.hand_landmarks)
            ]
            picked = select_hand(candidates, self._active_hand)
            if picked is not None:
                hand = HandFrame(landmarks=picked,
                                 handedness=self._active_hand)

        raw_d = None
        fres = self._face.detect_for_video(image, t_ms)
        face_detected = bool(fres.face_landmarks)
        if fres.face_landmarks:
            f = select_primary_face(fres.face_landmarks)
            if f is not None:
                r, l = f[_RIGHT_IRIS_CENTER], f[_LEFT_IRIS_CENTER]
                pupil_px = math.hypot((r.x - l.x) * w_px, (r.y - l.y) * h_px)
                if pupil_px > 1.0:
                    raw_d = estimate_distance_m(pupil_px, self._focal)
                    self._seen_face = True

        smoothed = self._smoother.update(raw_d) if self._seen_face else None
        return FrameResult(timestamp_ms=t_ms, hand=hand, face_distance_m=smoothed,
                           face_present=face_detected,
                           face_count=len(fres.face_landmarks or []),
                           hand_count=len(hres.hand_landmarks or []))

    def close(self) -> None:
        self._hands.close()
        self._face.close()
