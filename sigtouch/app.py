# sigtouch/app.py (Task 10 临时版, Task 12 重写)
import sys

from PySide6.QtWidgets import QApplication

from sigtouch.config import Config
from sigtouch.ui.preview import PreviewWindow
from sigtouch.vision import VisionThread


def main() -> None:
    app = QApplication(sys.argv)
    cfg = Config()
    vision = VisionThread(cfg)
    preview = PreviewWindow()
    vision.result_ready.connect(preview.update_result)
    vision.preview_frame.connect(preview.update_frame)
    vision.set_preview(True)
    vision.start()
    preview.show()
    app.aboutToQuit.connect(vision.stop)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
