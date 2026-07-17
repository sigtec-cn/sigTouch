# SigTouch 打包

前置:`pip install -e ".[dev]" && python scripts/download_models.py`

统一命令(在仓库根目录):

    pyinstaller packaging/sigtouch.spec

产物在 `dist/SigTouch/`(onedir:Qt 等动态库以独立文件存在,满足 LGPL)。

## 平台产物(在各自平台机器上执行)
- **Windows**:上述命令得到 `SigTouch.exe`;安装器用 Inno Setup 包装 `dist/SigTouch/`(后续脚本)。
- **macOS**:产出 `dist/SigTouch.app`;分发前需 `codesign` + 公证(后续处理);
  首次运行需在系统设置授权摄像头与辅助功能。
- **Linux**:`dist/SigTouch/` 可直接运行;AppImage 用 appimagetool 包装(后续脚本)。

## 已知限制
- Linux Wayland:输入注入受限(pynput),X11 会话全功能。
