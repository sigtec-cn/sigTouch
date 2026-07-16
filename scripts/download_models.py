# scripts/download_models.py
"""下载 MediaPipe Tasks 模型到 sigtouch/models/。构建与首次开发时运行一次。"""
import urllib.request
from pathlib import Path

MODELS = {
    "hand_landmarker.task":
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task",
    "face_landmarker.task":
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task",
}

def main() -> None:
    dest = Path(__file__).resolve().parent.parent / "sigtouch" / "models"
    dest.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        target = dest / name
        if target.exists():
            print(f"skip {name} (exists)")
            continue
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(url, target)
        print(f"  -> {target} ({target.stat().st_size // 1024} KB)")

if __name__ == "__main__":
    main()
