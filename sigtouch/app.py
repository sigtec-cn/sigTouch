# sigtouch/app.py
"""入口与装配:视觉线程 → 手势/映射 → 注入/渲染,托盘控制,看门狗,挂起门。"""
import logging
import subprocess
import sys
import time

from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config
from sigtouch.interaction import features as F
from sigtouch.interaction.gestures import GestureStateMachine
from sigtouch.interaction.hotkey import format_hotkey
from sigtouch.interaction.mapper import CursorMapper
from sigtouch.output.injector import Injector
from sigtouch.perception.distance import overlay_scale
from sigtouch.platformsupport import permissions as perms
from sigtouch.platformsupport.permissions import PermissionKind
from sigtouch.ui import native
from sigtouch.ui.overlay import OverlayWindow, target_screen_index
from sigtouch.ui.permission_wizard import PermissionWizard
from sigtouch.ui.preview import PreviewWindow
from sigtouch.ui.settings_dialog import SettingsDialog
from sigtouch.ui.tray import TrayController
from sigtouch.vision import VisionThread

_log = logging.getLogger(__name__)


class SuspendGate:
    """无人脸超过宽限期 → 挂起注入与渲染。"""

    def __init__(self, suspend_after_ms: int):
        self._after = suspend_after_ms
        self._last_face_ms: int | None = None

    def update(self, face_present: bool, t_ms: int) -> bool:
        if face_present:
            self._last_face_ms = t_ms
            return False
        if self._last_face_ms is None:
            return True
        return t_ms - self._last_face_ms > self._after


class _HotkeyBridge(QObject):
    """pynput 全局快捷键回调跑在监听线程,经 Qt 信号安全转到主线程。"""
    pressed = Signal()
    settings_pressed = Signal()


class QSettingsBackend:
    """把 QSettings 适配成 Config 需要的 get/__setitem__ 接口。"""

    def __init__(self):
        self._s = QSettings("sigTec", "SigTouch")

    def get(self, key, default=None):
        v = self._s.value(key)
        return default if v is None else v

    def __setitem__(self, key, value):
        self._s.setValue(key, value)


class SigTouchApp(QObject):
    def __init__(self, cfg: Config, show_preview: bool = False):
        super().__init__()
        self._cfg = cfg
        self._paused = False
        self._injector: Injector | None = None   # 辅助功能就绪后才构造
        self._overlay = OverlayWindow(cfg)
        self._overlay.apply_screen()
        self._preview = PreviewWindow()
        self._settings_dlg = SettingsDialog(cfg)
        self._settings_dlg.settings_applied.connect(self._apply_light_settings)
        self._settings_dlg.vision_restart_needed.connect(
            self._on_vision_restart_needed)
        self._tray = TrayController(self)
        self._tray.toggle_requested.connect(self._toggle_pause)
        self._tray.settings_requested.connect(self._show_settings)
        self._tray.preview_requested.connect(self._show_preview)
        self._tray.quit_requested.connect(self._quit)
        self._tray.permissions_requested.connect(self._show_wizard)

        self._hotkey_bridge = _HotkeyBridge()
        self._hotkey_bridge.pressed.connect(self._toggle_pause)
        self._hotkey_bridge.settings_pressed.connect(self._show_settings)
        self._hotkey_listener = None
        self._im_granted_at_start = perms.check(PermissionKind.INPUT_MONITORING)
        self._hotkey_needs_restart = False

        self._wizard = PermissionWizard(restart_hint=lambda: self._hotkey_needs_restart)
        self._wizard.restart_requested.connect(self._restart_app)
        self._wizard.all_granted.connect(self._on_permissions_changed)
        # 配置窗关闭后恢复纯托盘(accessory),不在 Dock 常驻
        self._settings_dlg.installEventFilter(self)
        self._wizard.installEventFilter(self)
        self._perm_timer = QTimer(self)
        self._perm_timer.timeout.connect(self._on_permissions_changed)

        self._ensure_capabilities()
        if not perms.all_granted():
            # 降级启动:引导窗 + 轮询;摄像头权限先主动触发系统首弹
            perms.request(PermissionKind.CAMERA)
            self._show_wizard()
            self._perm_timer.start(2000)

        self._detect_screen_size()
        self._build_interaction()
        self._vision: VisionThread | None = None
        self._start_vision()
        if show_preview:
            self._show_preview()
        self._ui_state = "active"
        self._refresh_tray_state()

        self._watchdog = QTimer(self)
        self._watchdog.timeout.connect(self._check_watchdog)
        self._watchdog.start(1000)

    # ---- 权限降级/激活 ----
    def _ensure_capabilities(self) -> None:
        """按当前权限构造缺失能力;可重入,权限就绪即激活,无需重启。"""
        if self._injector is None and perms.check(PermissionKind.ACCESSIBILITY):
            self._injector = Injector()
        if self._hotkey_listener is None and \
                perms.check(PermissionKind.INPUT_MONITORING):
            if self._im_granted_at_start:
                self._setup_hotkey()
            else:
                # 运行中才授予:不抢建 event tap——TCC 切换窗口内系统可能终止进程,
                # 且 macOS 要求重启应用权限才真正生效
                self._hotkey_needs_restart = True

    def _on_permissions_changed(self) -> None:
        self._ensure_capabilities()
        if perms.all_granted():
            self._perm_timer.stop()
        self._refresh_tray_state()

    def _show_wizard(self) -> None:
        self._present_window(self._wizard)

    def _detect_screen_size(self) -> None:
        """自动检测屏幕物理尺寸;检测不到且用户未确认过时,提示去设置。

        已检测/确认过(display/screen_diag_detected)则跳过,尊重用户手填值。
        仅在当前值仍是出厂默认时才自动写入检测结果,避免覆盖用户/外部已设的值。
        """
        if self._cfg.get("display/screen_diag_detected"):
            return
        # 无屏测试平台(offscreen/minimal)不做检测与提示
        if QGuiApplication.platformName() != "cocoa":
            return
        from sigtouch.config import DEFAULTS
        from sigtouch.platformsupport import screen
        diag = screen.detect_screen_diag_inch()
        at_factory_default = (
            self._cfg.get("display/screen_diag_inch")
            == DEFAULTS["display/screen_diag_inch"])
        if diag is not None:
            if at_factory_default:
                self._cfg.set("display/screen_diag_inch", diag)
                _log.info("自动检测屏幕对角线: %.1f 英寸", diag)
            self._cfg.set("display/screen_diag_detected", True)
            return
        # 检测失败:首次提示用户手动设置(不阻塞,用户可从托盘进设置)
        _log.info("屏幕尺寸无法自动检测,等待用户在设置中确认")
        QTimer.singleShot(1500, self._prompt_screen_size)

    def _prompt_screen_size(self) -> None:
        """延迟弹出提示:引导用户填屏幕尺寸(托盘应用,先激活再弹)。"""
        if self._cfg.get("display/screen_diag_detected"):
            return  # 期间已被设置/检测成功
        from PySide6.QtWidgets import QMessageBox
        native.set_activation_policy_regular()
        native.activate_app()
        box = QMessageBox(self._settings_dlg)
        box.setWindowTitle("请设置屏幕尺寸")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText("无法自动检测屏幕物理尺寸。\n"
                    "手影大小需要准确的屏幕对角线尺寸,请在设置「显示」页填写。")
        open_btn = box.addButton("打开设置", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("稍后", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        native.set_activation_policy_accessory()
        if box.clickedButton() is open_btn:
            self._show_settings()

    def _present_window(self, widget) -> None:
        """macOS 托盘 App 弹配置窗:先切 Regular 策略并拉到前台,窗口才置前获焦。

        LSUIElement 下 accessory 应用不激活,托盘菜单弹出的窗口会被压住且
        不响应输入;先激活再 show。窗口关闭由 _maybe_restore_accessory 恢复纯托盘。
        """
        native.set_activation_policy_regular()
        native.activate_app()
        widget.show()
        widget.raise_()
        widget.activateWindow()

    def _maybe_restore_accessory(self) -> None:
        """配置窗都关完后恢复 Accessory 纯托盘(不在 Dock 常驻)。"""
        if (self._settings_dlg.isVisible() or self._wizard.isVisible()):
            return
        native.set_activation_policy_accessory()

    def eventFilter(self, obj, event) -> bool:
        """监听配置窗 Hide:关窗后恢复 accessory 托盘策略。"""
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.Hide and obj in (
                self._settings_dlg, self._wizard):
            # 用 QTimer 延迟到事件循环空闲再判断,确保 isVisible 状态已更新
            QTimer.singleShot(0, self._maybe_restore_accessory)
        return super().eventFilter(obj, event)

    # ---- 构建/重建 ----
    def _build_interaction(self) -> None:
        screens = QGuiApplication.screens()
        idx = target_screen_index(self._cfg, screens)
        geo = screens[idx].geometry()
        self._machine = GestureStateMachine(self._cfg)
        self._mapper = CursorMapper(
            geo.width(), geo.height(),
            margin=self._cfg.get("interaction/box_margin"),
            freeze_ms=self._cfg.get("interaction/freeze_ms"),
            min_cutoff=self._cfg.get("interaction/smooth_min_cutoff"),
            beta=self._cfg.get("interaction/smooth_beta"),
            smooth_algo=self._cfg.get("interaction/smooth_algo"),
            kalman_process=self._cfg.get("interaction/kalman_process"),
            kalman_measure=self._cfg.get("interaction/kalman_measure"))
        self._screen_origin = (geo.x(), geo.y())
        self._gate = SuspendGate(
            int(self._cfg.get("interaction/suspend_after_s") * 1000))

    def _start_vision(self) -> None:
        self._vision = VisionThread(self._cfg)
        self._vision.result_ready.connect(self._on_result)
        self._vision.preview_frame.connect(self._preview.update_frame)
        self._vision.camera_error.connect(
            lambda _msg: self._apply_state("error"))
        self._vision.recovered.connect(self._refresh_tray_state)
        self._vision.set_preview(self._preview.isVisible())
        self._vision.start()

    def _restart_vision(self) -> None:
        self._stop_vision()
        self._start_vision()

    def _setup_hotkey(self) -> None:
        if self._hotkey_needs_restart:
            return  # 运行中才授予的输入监控:任何路径都不建 event tap,重启后生效
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if not perms.check(PermissionKind.INPUT_MONITORING):
            return  # 输入监控未授权:跳过,权限就绪后由 _ensure_capabilities 再启动
        mapping = {}
        pause = self._cfg.get("general/pause_hotkey").strip()
        if pause:
            mapping[pause] = self._hotkey_bridge.pressed.emit
        settings = self._cfg.get("general/settings_hotkey").strip()
        if settings and settings != pause:
            mapping[settings] = self._hotkey_bridge.settings_pressed.emit
        if not mapping:
            return
        from pynput import keyboard
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys(mapping)
            self._hotkey_listener.start()
        except Exception:
            _log.warning("全局快捷键注册失败(组合: %r),已禁用", list(mapping),
                        exc_info=True)  # 无效组合或系统权限缺失:禁用快捷键,不阻塞启动

    # ---- 每帧主流程 ----
    def _on_result(self, result) -> None:
        if self._vision is None:
            return  # 已暂停/摄像头已关:孤儿线程的尾帧直接丢弃
        self._preview.update_result(result)
        suspended = self._gate.update(result.face_present, result.timestamp_ms)
        if self._paused or suspended:
            for ev in self._machine.update(None, result.timestamp_ms):
                if self._injector is not None:
                    self._injector.dispatch(ev)
            if self._injector is not None:
                self._injector.release_all()
            self._overlay.clear()
            self._vision.set_idle(True)
            return
        self._vision.set_idle(False)

        events = self._machine.update(result.hand, result.timestamp_ms)
        if result.hand is not None:
            x, y = self._mapper.update(F.anchor_point(result.hand),
                                       self._machine.pinching,
                                       result.timestamp_ms)
            if self._injector is not None:
                self._injector.move(x + self._screen_origin[0],
                                    y + self._screen_origin[1])
            dist = result.face_distance_m if result.face_distance_m else 0.6
            scale = overlay_scale(
                dist, self._cfg.get("display/screen_diag_inch"),
                self._cfg.get("display/camera_screen_offset_m"),
                self._cfg.get("display/hand_scale_multiplier"))
            self._overlay.update_hand(result.hand, scale,
                                      self._machine.progress, cursor_px=(x, y))
        else:
            self._overlay.clear()
        for ev in events:
            if self._injector is not None:
                self._injector.dispatch(ev)

    # ---- 托盘/设置响应 ----
    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        if self._paused:
            if self._injector is not None:
                self._injector.release_all()
            self._overlay.clear()
            self._stop_vision()   # 暂停即关摄像头(省电/隐私),恢复时再开
        else:
            self._start_vision()  # 恢复:重新打开并连接摄像头
        self._refresh_tray_state()

    def _stop_vision(self) -> None:
        """停止视觉线程并断开信号(摄像头随之释放)。"""
        old = self._vision
        if old is None:
            return
        for sig in (old.result_ready, old.preview_frame,
                    old.camera_error, old.recovered):
            try:
                sig.disconnect()
            except RuntimeError:
                pass
        old.stop()
        self._vision = None

    def _current_state(self) -> str:
        """常规三态(error 为瞬时态,由 camera_error 信号单独驱动)。"""
        if self._paused:
            return "paused"
        if not perms.all_granted():
            return "permission"
        return "active"

    def _apply_state(self, state: str) -> None:
        """统一把状态同步到托盘与设置窗(带人读快捷键);_ui_state 是当前 UI 状态的唯一真源。"""
        self._ui_state = state
        raw = self._cfg.get("general/pause_hotkey").strip()
        hotkey = format_hotkey(raw) if raw else ""
        if hotkey and self._hotkey_needs_restart:
            hotkey = f"{hotkey}·需重启"
        self._tray.set_state(state, hotkey)
        self._settings_dlg.set_running_state(state)
        self._overlay.set_topmost(state == "active")

    def _refresh_tray_state(self) -> None:
        self._apply_state(self._current_state())

    def _show_settings(self) -> None:
        self._present_window(self._settings_dlg)
        self._settings_dlg.set_running_state(self._ui_state)
        self._settings_dlg.refresh_hotkey_label()

    def _show_preview(self) -> None:
        self._preview.show()
        if self._vision is not None:
            self._vision.set_preview(True)

    def _apply_light_settings(self) -> None:
        """设置即时生效的轻量路径:不重启视觉线程。"""
        # 先释放:_build_interaction() 会丢弃旧 GestureStateMachine,若正处于
        # DRAGGING 状态 DRAG_END 将永远不会发出,导致鼠标左键卡在按下状态。
        if self._injector is not None:
            self._injector.release_all()
        from sigtouch.platformsupport.autostart import set_autostart
        try:
            set_autostart(self._cfg.get("general/autostart"))
        except OSError:
            _log.warning("设置开机自启失败(权限不足等),不阻塞设置应用",
                        exc_info=True)
        self._build_interaction()
        self._overlay.apply_screen()
        self._setup_hotkey()
        self._refresh_tray_state()

    def _on_vision_restart_needed(self) -> None:
        """摄像头组/控制手改动:轻量应用 + 重启视觉线程。"""
        self._apply_light_settings()
        self._restart_vision()

    def _check_watchdog(self) -> None:
        if self._paused:
            return  # 暂停态摄像头本就关闭,不做存活重启
        if self._vision is None or not self._vision.isRunning():
            self._restart_vision()
            return
        # 预览窗被用户关掉后停发预览帧,省 CPU
        self._vision.set_preview(self._preview.isVisible())
        if self._ui_state == "active" and self._overlay.isVisible():
            self._overlay.raise_()  # 兜底:防止被后开窗口压住(macOS 另有原生层级)
        now = int(time.monotonic() * 1000)
        last = self._vision.last_frame_monotonic_ms
        if last and now - last > 5000:  # 5 秒无帧:管线卡死,重建
            self._restart_vision()

    def _restart_app(self) -> None:
        """重启自身(输入监控权限需重启生效)。拉起失败仅记录,不退出。"""
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable]
            else:
                cmd = [sys.executable, "-m", "sigtouch"]
            subprocess.Popen(cmd)
        except Exception:
            _log.warning("自动重启失败,请手动重启应用", exc_info=True)
            return
        self._quit()

    def _quit(self) -> None:
        self._watchdog.stop()
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        if self._vision is not None:
            self._vision.stop()
        if self._injector is not None:
            self._injector.release_all()
        QApplication.instance().quit()


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("SigTouch")
    from sigtouch.ui.theme import apply_theme
    apply_theme(app)
    from PySide6.QtWidgets import QMessageBox

    from sigtouch.perception.pipeline import MODELS_DIR
    missing = [n for n in ("hand_landmarker.task", "face_landmarker.task")
               if not (MODELS_DIR / n).exists()]
    if missing:
        box = QMessageBox(QMessageBox.Icon.Critical, "缺少模型文件",
                          "缺少 MediaPipe 模型: " + ", ".join(missing)
                          + "\n\n请先运行: python scripts/download_models.py")
        box.show()
        box.raise_()
        box.activateWindow()
        box.exec()
        sys.exit(1)

    cfg = Config(QSettingsBackend())
    controller = SigTouchApp(cfg, show_preview="--preview" in sys.argv[1:])
    _ = controller  # 持引用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
