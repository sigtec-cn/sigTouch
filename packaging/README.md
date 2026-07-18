# SigTouch 打包

前置:`pip install -e ".[dev]" && python scripts/download_models.py`

统一命令(在仓库根目录):

    pyinstaller packaging/sigtouch.spec

产物在 `dist/SigTouch/`(onedir:Qt 等动态库以独立文件存在,满足 LGPL)。

## 平台产物(在各自平台机器上执行)
- **Windows**:上述命令得到 `SigTouch.exe`;安装器用 Inno Setup 包装 `dist/SigTouch/`(后续脚本)。
- **macOS**:产出 `dist/SigTouch.app`(BUNDLE,含 NSCameraUsageDescription 等
  Info.plist 权限描述;同目录 `dist/SigTouch/` onedir 为中间产物);分发压缩
  `SigTouch.app`;`codesign` + 公证仍为后续工作,用户侧用 `xattr -cr` 解除隔离。
- **Linux**:`dist/SigTouch/` 可直接运行;AppImage 用 appimagetool 包装(后续脚本)。

## 已知限制
- Linux Wayland:输入注入受限(pynput),X11 会话全功能。

## 发布前手动 QA
打包产物无法被自动化测试覆盖真实摄像头/托盘/全局注入路径,发布前请按
`docs/manual-qa.md` 的 10 项检查清单人工验证。
