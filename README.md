# SigTouch

用摄像头把你的手变成鼠标:MediaPipe 识别手部与人眼,半透明手部轮廓投影到屏幕
(Oculus 风格,随人-屏距离自适应缩放),手势完成点击 / 拖拽 / 滚动 / 回车 / 退格。
常驻系统托盘,支持 Windows / macOS / Linux。MIT 协议。

## 手势

| 手势 | 动作 |
|---|---|
| 拇指+食指快捻 | 左键单击(捻住移动=拖拽) |
| 拇指+中指快捻 | 右键单击 |
| 三指捻住上下移动 | 滚动 |
| OK 手势保持 0.5s | 回车 |
| 张开手掌前推 | 退格 |
| Ctrl+Alt+P | 暂停/恢复 |

## 下载安装

从 [Releases](../../releases) 下载对应平台压缩包,解压后运行 `SigTouch`:

- **Windows**:解压 `SigTouch-*-win64.zip`,运行 `SigTouch\SigTouch.exe`。
- **macOS**:解压 `SigTouch-*-macos-arm64.zip` 得到 `SigTouch.app`;产物未签名,
  首次运行前解除隔离:`xattr -cr SigTouch.app`,然后双击(或 `open SigTouch.app`)启动。
  启动后按权限引导窗逐项授权摄像头、辅助功能、输入监控(授权后自动激活,无需重启);
  系统权限面板中显示的应用名即为 SigTouch。
- **Linux (X11)**:解压 `SigTouch-*-linux-x64.tar.gz`,运行 `SigTouch/SigTouch`。
  Wayland 下输入注入受限(已知限制)。

## 开发

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python scripts/download_models.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v
.venv/bin/python -m sigtouch --preview   # 带调试预览窗启动
```

打包:`pyinstaller packaging/sigtouch.spec`(详见 `packaging/README.md`);
设计文档见 `docs/superpowers/specs/`,手动 QA 清单见 `docs/manual-qa.md`。
