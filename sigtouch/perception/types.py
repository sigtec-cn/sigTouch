from dataclasses import dataclass

Landmark = tuple[float, float, float]  # 归一化图像坐标 (x右, y下, z), 画面已镜像


@dataclass(frozen=True)
class HandFrame:
    landmarks: list[Landmark]  # 21 点, MediaPipe Hand Landmarker 索引
    handedness: str            # "Left" | "Right"


@dataclass(frozen=True)
class FrameResult:
    timestamp_ms: int
    hand: HandFrame | None
    face_distance_m: float | None  # 平滑后的人-屏距离; 从未见过人脸时为 None
    face_present: bool = False     # 本帧是否检出人脸(无人自动挂起判定用)
