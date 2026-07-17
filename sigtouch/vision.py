# sigtouch/vision.py
"""视觉线程:摄像头采集(断线重连)+ MediaPipe 推理,发出 FrameResult。"""
import time

import cv2
from PySide6.QtCore import QThread, Signal

from sigtouch.config import Config
from sigtouch.perception.pipeline import PerceptionPipeline


class VisionThread(QThread):
    result_ready = Signal(object)   # FrameResult
    preview_frame = Signal(object)  # BGR ndarray(已镜像)
    camera_error = Signal(str)
    recovered = Signal()

    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self._cfg = cfg
        self._running = True
        self._idle = False
        self._preview = False
        self.last_frame_monotonic_ms = 0

    def set_idle(self, idle: bool) -> None:
        self._idle = idle

    def set_preview(self, on: bool) -> None:
        self._preview = on

    def stop(self) -> None:
        self._running = False
        self.wait(3000)

    def _interruptible_sleep(self, seconds: float) -> None:
        """分片睡眠,stop() 置 _running=False 后最多 0.1s 内退出。"""
        deadline = time.monotonic() + seconds
        while self._running:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.1, remaining))

    def _open_camera(self):
        cap = cv2.VideoCapture(self._cfg.get("camera/index"))
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._cfg.get("camera/width"))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._cfg.get("camera/height"))
        return cap

    def run(self) -> None:
        try:
            pipeline = PerceptionPipeline(self._cfg.get("camera/width"),
                                          self._cfg.get("camera/fov_deg"))
        except Exception as exc:  # 模型缺失/损坏:进入错误待机而非死亡,避免看门狗每秒重启
            self.camera_error.emit(f"感知模型加载失败: {exc}")
            while self._running:
                self._interruptible_sleep(1.0)
            return
        cap = None
        backoff = 1.0
        had_error = False
        try:
            while self._running:
                if cap is None:
                    cap = self._open_camera()
                    if cap is None:
                        if not had_error:
                            self.camera_error.emit("无法打开摄像头")
                            had_error = True
                        self._interruptible_sleep(backoff)
                        backoff = min(backoff * 2.0, 10.0)
                        continue
                    backoff = 1.0
                    if had_error:
                        self.recovered.emit()
                        had_error = False
                ok, frame = cap.read()
                if not ok:
                    cap.release()
                    cap = None
                    self.camera_error.emit("摄像头读取失败,重连中")
                    had_error = True
                    self._interruptible_sleep(backoff)
                    backoff = min(backoff * 2.0, 10.0)
                    continue
                frame = cv2.flip(frame, 1)  # 镜像:下游一律假设已翻转
                t_ms = int(time.monotonic() * 1000)
                self.last_frame_monotonic_ms = t_ms
                self.result_ready.emit(pipeline.process(frame, t_ms))
                if self._preview:
                    self.preview_frame.emit(frame)
                if self._idle:
                    self._interruptible_sleep(0.2)  # 挂起态 ~5fps,仅维持人脸检测
        finally:
            if cap is not None:
                cap.release()
            pipeline.close()
