# packaging/sigtouch.spec
# 用法: pyinstaller packaging/sigtouch.spec  (在仓库根目录执行)
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("mediapipe")          # mediapipe 自带资源
datas += [("../sigtouch/models", "sigtouch/models")]  # .task 模型

a = Analysis(
    ["../sigtouch/__main__.py"],
    pathex=[".."],
    datas=datas,
    # darwin 权限检测的 pyobjc 框架;其他平台构建时仅产生 not-found 警告
    hiddenimports=["AVFoundation", "ApplicationServices"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts,
    exclude_binaries=True,       # onedir:二进制留在 COLLECT(LGPL 合规)
    name="SigTouch",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SigTouch")

app = BUNDLE(
    coll,
    name="SigTouch.app",
    bundle_identifier="cn.sigtec.sigtouch",
    info_plist={
        "NSCameraUsageDescription":
            "SigTouch 需要摄像头识别手势以控制鼠标和键盘。",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    },
)
