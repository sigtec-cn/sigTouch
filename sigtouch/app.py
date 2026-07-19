# sigtouch/app.py
"""入口与装配:视觉线程 → 手势/映射 → 注入/渲染,托盘控制,看门狗,挂起门。"""
import logging
import sys
import time

from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from sigtouch.config import Config
from sigtouch.interaction import features as F
from sigtouch.interaction.gestures import GestureStateMachine
from sigtouch.interaction.mapper import CursorMapper
from sigtouch.output.injector import Injector
from sigtouch.perception.distance import overlay_scale
from sigtouch.platformsupport import permissions as perms
from sigtouch.platformsupport.permissions import PermissionKind
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
        self._settings_dlg.settings_applied.connect(self._on_settings_applied)
        self._tray = TrayController(self)
        self._tray.toggle_requested.connect(self._toggle_pause)
        self._tray.settings_requested.connect(self._settings_dlg.show)
        self._tray.preview_requested.connect(self._show_preview)
        self._tray.quit_requested.connect(self._quit)
        self._tray.permissions_requested.connect(self._show_wizard)

        self._hotkey_bridge = _HotkeyBridge()
        self._hotkey_bridge.pressed.connect(self._toggle_pause)
        self._hotkey_listener = None

        self._wizard = PermissionWizard()
        self._wizard.all_granted.connect(self._on_permissions_changed)
        self._perm_timer = QTimer(self)
        self._perm_timer.timeout.connect(self._on_permissions_changed)

        self._ensure_capabilities()
        if not perms.all_granted():
            # 降级启动:引导窗 + 轮询;摄像头权限先主动触发系统首弹
            perms.request(PermissionKind.CAMERA)
            self._show_wizard()
            self._perm_timer.start(2000)

        self._build_interaction()
        self._vision: VisionThread | None = None
        self._start_vision()
        if show_preview:
            self._show_preview()
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
            self._setup_hotkey()

    def _on_permissions_changed(self) -> None:
        self._ensure_capabilities()
        if perms.all_granted():
            self._perm_timer.stop()
        self._refresh_tray_state()

    def _show_wizard(self) -> None:
        self._wizard.show()
        self._wizard.raise_()
        self._wizard.activateWindow()

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
            beta=self._cfg.get("interaction/smooth_beta"))
        self._screen_origin = (geo.x(), geo.y())
        self._gate = SuspendGate(
            int(self._cfg.get("interaction/suspend_after_s") * 1000))

    def _start_vision(self) -> None:
        self._vision = VisionThread(self._cfg)
        self._vision.result_ready.connect(self._on_result)
        self._vision.preview_frame.connect(self._preview.update_frame)
        self._vision.camera_error.connect(
            lambda _msg: self._tray.set_state("error"))
        self._vision.recovered.connect(self._refresh_tray_state)
        self._vision.set_preview(self._preview.isVisible())
        self._vision.start()

    def _restart_vision(self) -> None:
        old = self._vision
        if old is not None:
            # 先断开信号:即使旧线程卡在 cap.read() 未能退出,
            # 也不会再驱动 _on_result(孤儿线程 _running=False,读取返回后自行结束)
            for sig in (old.result_ready, old.preview_frame,
                        old.camera_error, old.recovered):
                try:
                    sig.disconnect()
                except RuntimeError:
                    pass  # 无连接可断
            old.stop()
        self._start_vision()

    def _setup_hotkey(self) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
        if not perms.check(PermissionKind.INPUT_MONITORING):
            return  # 输入监控未授权:跳过,权限就绪后由 _ensure_capabilities 再启动
        combo = self._cfg.get("general/pause_hotkey").strip()
        if not combo:
            return
        from pynput import keyboard
        try:
            self._hotkey_listener = keyboard.GlobalHotKeys(
                {combo: self._hotkey_bridge.pressed.emit})
            self._hotkey_listener.start()
        except Exception:
            _log.warning("全局快捷键注册失败(组合: %r),已禁用", combo,
                        exc_info=True)  # 无效组合或系统权限缺失:禁用快捷键,不阻塞启动

    # ---- 每帧主流程 ----
    def _on_result(self, result) -> None:
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
            scale = overlay_scale(dist,
                                  self._cfg.get("display/screen_diag_inch"))
            self._overlay.update_hand(result.hand, scale,
                                      self._machine.feedback, cursor_px=(x, y))
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
            self._vision.set_idle(True)
        self._refresh_tray_state()

    def _refresh_tray_state(self) -> None:
        if self._paused:
            self._tray.set_state("paused")
        elif not perms.all_granted():
            self._tray.set_state("permission")
        else:
            self._tray.set_state("active")

    def _show_preview(self) -> None:
        self._preview.show()
        self._vision.set_preview(True)

    def _on_settings_applied(self) -> None:
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
        self._restart_vision()

    def _check_watchdog(self) -> None:
        if self._vision is None or not self._vision.isRunning():
            self._restart_vision()
            return
        # 预览窗被用户关掉后停发预览帧,省 CPU
        self._vision.set_preview(self._preview.isVisible())
        if self._overlay.isVisible():
            self._overlay.raise_()  # 兜底:防止被后开窗口压住(macOS 另有原生层级)
        now = int(time.monotonic() * 1000)
        last = self._vision.last_frame_monotonic_ms
        if last and now - last > 5000:  # 5 秒无帧:管线卡死,重建
            self._restart_vision()

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
        QMessageBox.critical(
            None, "缺少模型文件",
            "缺少 MediaPipe 模型: " + ", ".join(missing)
            + "\n\n请先运行: python scripts/download_models.py")
        sys.exit(1)

    cfg = Config(QSettingsBackend())
    controller = SigTouchApp(cfg, show_preview="--preview" in sys.argv[1:])
    _ = controller  # 持引用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
