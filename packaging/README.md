# SigTouch 打包

前置:`pip install -e ".[dev]" && python scripts/download_models.py`

统一命令(在仓库根目录):

    pyinstaller packaging/sigtouch.spec

产物在 `dist/SigTouch/`(onedir:Qt 等动态库以独立文件存在,满足 LGPL)。

## 平台产物(在各自平台机器上执行)
- **Windows**:上述命令得到 `SigTouch.exe`;安装器用 Inno Setup 包装 `dist/SigTouch/`(后续脚本)。
- **macOS**:产物为 `dist/SigTouch/`(onedir 目录,内含 `SigTouch` 可执行文件),直接运行即可;
  打包成 `.app` bundle(PyInstaller BUNDLE 步骤)与 `codesign` + 公证属于后续工作;
  首次运行需在系统设置授权摄像头与辅助功能。
- **Linux**:`dist/SigTouch/` 可直接运行;AppImage 用 appimagetool 包装(后续脚本)。

## 已知限制
- Linux Wayland:输入注入受限(pynput),X11 会话全功能。

## 发布前手动 QA
打包产物无法被自动化测试覆盖真实摄像头/托盘/全局注入路径,发布前请按
`docs/manual-qa.md` 的 10 项检查清单人工验证。
