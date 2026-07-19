# scripts/generate_icons.py
"""生成应用图标资产(青绿圆底 + 白色手掌,与托盘图标同族)。
本地运行一次,产物提交入库,构建机不需要 Pillow:
    .venv/bin/python scripts/generate_icons.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ACCENT = (20, 184, 166, 255)   # #14B8A6
WHITE = (255, 255, 255, 255)
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def draw_master(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size * 0.04
    d.ellipse([m, m, size - m, size - m], fill=ACCENT)
    s = size / 64.0  # 与托盘 64px 几何同族
    d.ellipse([20 * s, 30 * s, 44 * s, 52 * s], fill=WHITE)
    for x, h in ((14, 14), (22, 18), (30, 20), (38, 18), (46, 13)):
        d.rounded_rectangle([x * s, (34 - h) * s, (x + 6) * s, 34 * s],
                            radius=3 * s, fill=WHITE)
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    master = draw_master()
    master.save(ASSETS / "icon.ico",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                       (128, 128), (256, 256)])
    print("wrote", ASSETS / "icon.ico")
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as td:
            iconset = Path(td) / "icon.iconset"
            iconset.mkdir()
            for sz in (16, 32, 64, 128, 256, 512):
                master.resize((sz, sz)).save(iconset / f"icon_{sz}x{sz}.png")
                master.resize((sz * 2, sz * 2)).save(
                    iconset / f"icon_{sz}x{sz}@2x.png")
            subprocess.run(["iconutil", "-c", "icns", str(iconset),
                            "-o", str(ASSETS / "icon.icns")], check=True)
        print("wrote", ASSETS / "icon.icns")


if __name__ == "__main__":
    main()
