# SigTouch v1.1 设计文档:权限引导与 CI 分发

日期:2026-07-17
状态:已确认
关联:v1 设计见 `2026-07-16-sigtouch-design.md`

## 1. 背景与目标

**问题**:v1 在 macOS 上启动时,若缺辅助功能权限只弹一个警告框(文案要求"授权后重启"),关闭后应用虽在托盘存活但注入静默失效;摄像头与输入监控权限完全没有检测与引导。用户感知为"提示权限不足然后关闭"。

**目标**:
1. 启动永不因权限问题退出或假死:显示权限引导 UI,逐项引导用户开通,后台自动轮询检查,权限就绪后自动激活对应能力,无需重启。
2. GitHub Actions 三平台自动构建;打 tag 自动发布到 GitHub Releases 分发(已确认不用 GitHub Packages——其不支持桌面二进制分发)。

## 2. 决策记录

| 决策 | 结论 |
|---|---|
| 分发渠道 | GitHub Releases(tag `v*` 触发);GitHub Packages 不适用 |
| 权限未就绪时的应用状态 | 降级运行 + 自动激活:引导窗可关、托盘存活、每 2s 自动重检、就绪即激活 |
| macOS 权限检测机制 | 方案 A:`pyobjc-framework-AVFoundation`(仅 darwin)查摄像头授权;`pyobjc-framework-ApplicationServices` 调 `AXIsProcessTrustedWithOptions`(辅助功能,含触发弹窗;纯 ctypes 构造 CFDictionary 过于脆弱);ctypes 调 IOKit `IOHIDCheckAccess`(输入监控) |
| macOS 产物签名 | 仍为后续工作;README 注明 `xattr -cr` 解除隔离 |

## 3. 权限模型

三项权限,均仅 macOS 需要;Windows/Linux 上 `check()` 恒为已授权:

| 权限 | 用途 | 检测 | 主动请求 | 系统设置深链 |
|---|---|---|---|---|
| CAMERA | 视觉管线采集 | `AVCaptureDevice.authorizationStatusForMediaType_("vide")` | `requestAccessForMediaType_completionHandler_`(触发系统弹窗) | `x-apple.systempreferences:com.apple.preference.security?Privacy_Camera` |
| ACCESSIBILITY | pynput 鼠标/键盘注入 | `AXIsProcessTrusted()`(ctypes) | `AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})`(触发系统弹窗) | `...?Privacy_Accessibility` |
| INPUT_MONITORING | pynput GlobalHotKeys 全局快捷键监听 | IOKit `IOHIDCheckAccess(kIOHIDRequestTypeListenEvent)`(ctypes) | `IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)` | `...?Privacy_ListenEvent` |

依赖变更:`pyproject.toml` 增加(均仅 darwin):
`pyobjc-framework-AVFoundation>=10.0; sys_platform == 'darwin'` 与
`pyobjc-framework-ApplicationServices>=10.0; sys_platform == 'darwin'`。

### 3.1 permissions 模块接口(重写 `sigtouch/platformsupport/permissions.py`)

```python
class PermissionKind(Enum):
    CAMERA = ...; ACCESSIBILITY = ...; INPUT_MONITORING = ...

def check(kind: PermissionKind) -> bool          # 非 macOS 恒 True;检测失败 fail-open 返回 True 并 log.warning
def request(kind: PermissionKind) -> None        # 触发系统授权弹窗;非 macOS no-op;异常吞掉并 log
def open_settings(kind: PermissionKind) -> None  # QDesktopServices.openUrl 深链;非 macOS no-op
def snapshot() -> dict[PermissionKind, bool]     # 三项一次性检测
def all_granted() -> bool
# 兼容保留:accessibility_ok() = check(ACCESSIBILITY)(现有调用点迁移后删除)
```

约束:`IOHIDCheckAccess` 返回值语义为 0=granted/1=denied/2=unknown,unknown 视为未授权(需要引导);任何 ctypes/pyobjc 异常都不得抛出到调用方——fail-open 为 True 并记录日志,保证异常环境(旧系统、SIP 变化)下应用可用。

## 4. 权限引导窗(新增 `sigtouch/ui/permission_wizard.py`)

`PermissionWizard(QDialog)`:

- 每项权限一行:名称、一句话用途说明、状态图标(✓ 绿 / ✗ 红)、[请求权限] 按钮(调 `request`,已授权则禁用)、[打开系统设置] 按钮(调 `open_settings`)。
- `QTimer` 每 2000ms 调 `snapshot()` 刷新全部行;检测函数可注入(构造参数 `checker=snapshot`)以便离屏测试。
- 全部就绪:显示"✓ 全部权限已就绪"横幅,发出 `all_granted` 信号,2 秒后自动关闭。
- 窗口可随时关闭(关闭仅隐藏窗口,不影响后台轮询与降级逻辑);信号 `all_granted` 只在从"未全部就绪"变为"全部就绪"的沿上发一次。
- 非 macOS 平台:`snapshot()` 全 True,向导即刻显示全部就绪(实际场景中 app 不会弹它)。

托盘菜单新增"权限设置…"项(位于"设置…"之后),随时可重新打开向导。

## 5. 应用降级状态机(修改 `sigtouch/app.py`)

### 5.1 启动流程(替换现有 QMessageBox.warning 逻辑)

```
main():
  QApplication → 模型检查(不变) → 构造 SigTouchApp
SigTouchApp.__init__:
  权限快照 snapshot()
  ├─ 全部就绪 → 与 v1 相同的完整启动
  └─ 有缺失   → 降级启动:
       · 托盘显示新状态 "permission"(黄色图标,tooltip "SigTouch:等待权限授权")
       · 弹出 PermissionWizard
       · 不构造 Injector、不启动全局快捷键(见 5.2)
       · VisionThread 照常启动(CAMERA 未授权时 request(CAMERA) 先触发系统弹窗;
         打开失败走既有 camera_error 重试路径,授权后自动恢复)
       · 启动权限轮询 QTimer(2s):任一项从缺失变就绪 → 激活对应能力
```

### 5.2 能力门控(根因修复)

- **注入门控**:`self._injector` 初始为 None;仅当 `check(ACCESSIBILITY)` 为 True 时才构造(pynput 懒加载因此也被推迟,消除未授权时可能的构造异常)。`_on_result` 内所有 `self._injector.*` 调用改经 `_injector_safe()`(None 时跳过注入,其余流程——Overlay 渲染、手势状态机——照常,用户能看到手部轮廓但点击不生效,向导里能看到缺哪项)。
- **快捷键门控**:`_setup_hotkey()` 前置 `check(INPUT_MONITORING)`,未就绪直接跳过(保留现有 except Exception 兜底)。
- **激活路径**:权限轮询或向导 `all_granted` 信号触发 `_on_permissions_changed()`:构造缺失的 Injector、启动快捷键、托盘恢复 active 态、停止轮询(全部就绪后)。**无需重启应用。**
- **不变式**:权限相关的任何异常都不得使 `main()`/`__init__` 抛出;托盘与设置窗在任何权限状态下都可用。

### 5.3 托盘状态扩展

`TrayController.set_state` 增加 `"permission"` 态:黄色图标(`#f1c40f`)、tooltip "SigTouch:等待权限授权"、菜单文案不变。

## 6. GitHub Actions

### 6.1 `.github/workflows/ci.yml`(push / PR → main)

矩阵 `os: [ubuntu-latest, macos-latest, windows-latest]`,Python 3.12:

1. checkout + setup-python(pip 缓存)
2. Linux 追加系统库:`libegl1 libgl1 libxkbcommon-x11-0 libxcb-*`(PySide6 offscreen 所需)
3. `pip install -e ".[dev]"`
4. `python scripts/download_models.py`(缓存 `sigtouch/models/*.task`,key 为脚本哈希)
5. `pytest tests/ -v`(env `QT_QPA_PLATFORM=offscreen`)
6. `pyinstaller packaging/sigtouch.spec`
7. `actions/upload-artifact` 上传 `dist/SigTouch/`(验证三平台可构建,保留 7 天)

### 6.2 `.github/workflows/release.yml`(push tag `v*`)

同矩阵构建后打包并发布:

- Windows:`SigTouch-${tag}-win64.zip`(Compress-Archive)
- macOS:`SigTouch-${tag}-macos-arm64.zip`(ditto/zip)
- Linux:`SigTouch-${tag}-linux-x64.tar.gz`
- `softprops/action-gh-release@v2` 创建 Release、自动生成 release notes、挂载三产物(`permissions: contents: write`)

### 6.3 文档

README(新建仓库根 README.md,当前缺失)包含:项目简介、Release 下载安装三平台说明、macOS 首次运行 `xattr -cr SigTouch` 解除隔离与权限授权说明、开发环境搭建(python3.12 venv、模型下载、测试命令)。

## 7. 测试策略

- `permissions`:非 macOS 路径(全 True、no-op)与接口契约单测;macOS ctypes/pyobjc 分支 fail-open 行为用异常注入测试;真机行为人工 QA。
- `PermissionWizard`:offscreen + 注入假 checker——初始部分缺失渲染 ✗、假 checker 翻转后轮询刷新为 ✓、`all_granted` 恰好发一次、按钮调用被记录。
- `app` 降级/激活:扩展 `tests/test_app_frame_path.py` harness——权限缺失时构造 SigTouchApp 不抛异常、`_on_result` 在 injector 为 None 时不注入但 Overlay 正常、模拟权限就绪后 `_on_permissions_changed` 构造注入器并恢复。
- CI 工作流:推送后以真实 Actions 运行为验证;本地仅做 YAML 语法与 act 不可用性说明。
- 人工 QA 追加清单项(`docs/manual-qa.md`):全新 macOS 授权流程走查(逐项授权→自动激活,全程不重启)。

## 8. 明确不做(v1.1)

- macOS 代码签名与公证(README 注明 xattr 方案)。
- Windows Inno 安装器 / Linux AppImage(Releases 直接分发 zip/tar.gz)。
- 权限被"运行中撤销"的实时降级(系统会杀死进程或注入失效,v1.1 只保证下次启动正确引导)。
- Intel macOS 构建(macos-latest 为 arm64;如需 x86_64 后续加 macos-13 矩阵)。
