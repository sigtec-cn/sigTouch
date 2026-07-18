# sigtouch/ui/preview.py
"""调试预览窗:显示镜像画面 + 手部关键点/锚点/捏合状态,调阈值用。"""
import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from sigtouch.interaction import features as F

_HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # 拇指
    (0, 5), (5, 6), (6, 7), (7, 8),          # 食指
    (5, 9), (9, 10), (10, 11), (11, 12),     # 中指
    (9, 13), (13, 14), (14, 15), (15, 16),   # 无名指
    (13, 17), (17, 18), (18, 19), (19, 20),  # 小指
    (0, 17),
]


class PreviewWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SigTouch 调试预览")
        self._label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        self._last_result = None

    def update_result(self, result) -> None:
        self._last_result = result

    def update_frame(self, bgr) -> None:
        h, w = bgr.shape[:2]
        r = self._last_result
        if r is not None and r.hand is not None:
            pts = [(int(x * w), int(y * h)) for x, y, _ in r.hand.landmarks]
            for a, b in _HAND_CONNECTIONS:
                cv2.line(bgr, pts[a], pts[b], (0, 255, 0), 2)
            ax, ay = F.anchor_point(r.hand)
            cv2.circle(bgr, (int(ax * w), int(ay * h)), 8, (0, 0, 255), -1)
            cv2.putText(bgr, f"pinch={F.pinch_ratio(r.hand, F.INDEX_TIP):.2f}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(bgr, f"hand={r.hand.handedness}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        if r is not None and r.face_distance_m is not None:
            cv2.putText(bgr, f"dist={r.face_distance_m:.2f}m", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self._label.setPixmap(QPixmap.fromImage(img))
