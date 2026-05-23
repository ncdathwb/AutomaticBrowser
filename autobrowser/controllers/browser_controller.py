import logging
import threading

import psutil
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from selenium.common.exceptions import WebDriverException

from autobrowser.browser.automation import TARGET_URL, ExternalLoginRequired, run_browser_logic
from autobrowser.browser.automation_flow import FlowError, load_flow
from autobrowser.browser.external_chrome import launch_external_chrome
from autobrowser.browser.session import (
    BrowserSession,
    create_browser_session,
    get_process_tree_pids,
)
from autobrowser.config import APP_CONFIG
from autobrowser.platform.win32_window import (
    embed_window,
    focus_embedded_window,
    release_embedded_window,
    resize_embedded_window,
    stop_taskbar_flash,
)

logger = logging.getLogger(__name__)
AUTOMATION_LOGGER_NAME = "autobrowser.browser.automation"

HEALTH_CHECK_INTERVAL_MS = 60_000
RESOURCE_CHECK_INTERVAL_MS = 5_000
MEMORY_WARNING_MB = 1024


class SignalLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__(logging.INFO)
        self.signal = signal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.signal.emit(self.format(record))
        except Exception:
            self.handleError(record)


class BrowserController(QObject):
    log_message = pyqtSignal(str)
    status_changed = pyqtSignal(str, str)
    placeholder_text_changed = pyqtSignal(str)
    placeholder_visibility_changed = pyqtSignal(bool)
    external_login_visibility_changed = pyqtSignal(bool)
    browser_embed_requested = pyqtSignal(int)
    browser_resize_requested = pyqtSignal()
    startup_failed = pyqtSignal(str)
    resource_update = pyqtSignal(float, float)

    _browser_ready = pyqtSignal(object)
    _navigation_worker_finished = pyqtSignal(str)
    _external_login_required = pyqtSignal(str, str)
    _startup_worker_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.session: BrowserSession | None = None
        self.browser_thread: threading.Thread | None = None
        self.navigation_thread: threading.Thread | None = None
        self.resize_timer: QTimer | None = None
        self.taskbar_flash_timer: QTimer | None = None
        self._health_check_timer: QTimer | None = None
        self._resource_timer: QTimer | None = None
        self.window_hwnd: int | None = None
        self.external_login_url = TARGET_URL
        self.is_closing = False
        self.flow_path: str | None = None
        self._recovering = False
        self._recovery_count = 0

        self._browser_ready.connect(self._on_browser_ready)
        self._navigation_worker_finished.connect(self._on_navigation_finished)
        self._external_login_required.connect(self._on_external_login_required)
        self._startup_worker_failed.connect(self._on_startup_failed)

    def start(self, window_hwnd: int) -> None:
        self.window_hwnd = window_hwnd
        self.start_browser()
        self.start_taskbar_flash_guard()

    def start_browser(self) -> None:
        if self.browser_thread and self.browser_thread.is_alive():
            return

        self.placeholder_text_changed.emit("Đang khởi động trình duyệt...")
        self.placeholder_visibility_changed.emit(True)
        self.status_changed.emit("Đang khởi động", "#f0b84f")
        self.log_message.emit("Đang khởi động trình duyệt...")

        self.browser_thread = threading.Thread(
            target=self._create_browser_worker,
            daemon=True,
        )
        self.browser_thread.start()

    def _create_browser_worker(self) -> None:
        try:
            session = create_browser_session()
            self._browser_ready.emit(session)
        except Exception as e:
            logger.exception("Không tạo được phiên trình duyệt")
            self._startup_worker_failed.emit(str(e))

    def _on_browser_ready(self, session: BrowserSession) -> None:
        if self.is_closing:
            with session.lock:
                session.driver.quit()
            return

        self.session = session

        if not session.hwnd:
            self.placeholder_text_changed.emit(
                "Chrome đang chạy nhưng chưa nhúng được vào giao diện"
            )
            self.status_changed.emit("Lỗi nhúng", "#ff6b6b")
            self.log_message.emit("Không tìm thấy mã cửa sổ Chrome để nhúng vào giao diện.")
            return

        self.browser_embed_requested.emit(session.hwnd)
        self.start_navigation()

    def embed_browser(
        self,
        child_hwnd: int,
        parent_hwnd: int,
        width: int,
        height: int,
    ) -> None:
        try:
            self.placeholder_visibility_changed.emit(False)
            embed_window(child_hwnd, parent_hwnd)
            self.resize_browser(width, height)
            QTimer.singleShot(250, lambda: self.browser_resize_requested.emit())
            QTimer.singleShot(750, lambda: self.browser_resize_requested.emit())
            self.start_resize_timer()
            self.status_changed.emit("Đã kết nối", "#5ee089")
            self.log_message.emit("Trình duyệt đã sẵn sàng.")
        except Exception as e:
            logger.exception("Không nhúng được cửa sổ Chrome")
            self.status_changed.emit("Lỗi", "#ff6b6b")
            self.log_message.emit(f"Lỗi khi nhúng Chrome: {e}")

    def start_navigation(self) -> None:
        if not self.session:
            return

        self.navigation_thread = threading.Thread(
            target=self._navigate_worker,
            daemon=True,
        )
        self.navigation_thread.start()

    def set_flow(self, flow_path: str) -> None:
        """Use a YAML flow file instead of the built-in automation logic."""
        self.flow_path = flow_path

    def _navigate_worker(self) -> None:
        automation_logger = logging.getLogger(AUTOMATION_LOGGER_NAME)
        automation_handler = SignalLogHandler(self.log_message)
        automation_handler.setFormatter(logging.Formatter("Tự động hóa: %(message)s"))
        automation_logger.addHandler(automation_handler)

        try:
            if self.is_closing or not self.session:
                return

            if self.flow_path:
                self._run_flow_worker()
            else:
                current_url = run_browser_logic(self.session, APP_CONFIG.data_dir)
                self._navigation_worker_finished.emit(current_url)
        except ExternalLoginRequired as e:
            logger.info("Cần đăng nhập ngoài: %s", e.url)
            self._external_login_required.emit(e.url, e.message)
        except (WebDriverException, OSError) as e:
            logger.exception("Không chạy được luồng điều hướng trình duyệt")
            self.log_message.emit(f"Lỗi điều hướng trình duyệt: {e}")
        finally:
            automation_logger.removeHandler(automation_handler)
            automation_handler.close()

    def _run_flow_worker(self) -> None:
        from pathlib import Path

        from autobrowser.browser.automation_flow import execute_flow

        flow_path = Path(self.flow_path)  # type: ignore[arg-type]
        flow = load_flow(flow_path)
        self.log_message.emit(f"Chạy flow: {flow.name} ({len(flow.steps)} bước)")

        session = self.session
        assert session is not None

        with session.lock:
            execute_flow(session.driver, flow)

        self._navigation_worker_finished.emit(session.driver.current_url)

    def _on_navigation_finished(self, _current_url: str) -> None:
        self.browser_resize_requested.emit()
        QTimer.singleShot(300, lambda: self.browser_resize_requested.emit())
        self.start_health_check()
        self.start_resource_monitor()

    def _on_external_login_required(self, url: str, message: str) -> None:
        if self.is_closing:
            return

        self.show_external_login_prompt(
            status_text="Cần đăng nhập ngoài",
            message=message,
            url=url,
        )

    def start_resize_timer(self) -> None:
        if self.resize_timer:
            self.resize_timer.stop()

        self.resize_timer = QTimer(self)
        self.resize_timer.timeout.connect(self.browser_resize_requested.emit)
        self.resize_timer.start(APP_CONFIG.resize_interval_ms)

    def start_taskbar_flash_guard(self) -> None:
        if self.taskbar_flash_timer:
            self.taskbar_flash_timer.stop()

        self.taskbar_flash_timer = QTimer(self)
        self.taskbar_flash_timer.timeout.connect(self.stop_taskbar_attention)
        self.taskbar_flash_timer.start(APP_CONFIG.taskbar_flash_guard_interval_ms)

    def stop_taskbar_attention(self) -> None:
        if not self.window_hwnd:
            return

        try:
            stop_taskbar_flash(self.window_hwnd)
        except Exception:
            logger.debug("Không tắt được trạng thái nhấp nháy trên thanh tác vụ", exc_info=True)

    def start_health_check(self) -> None:
        if self._health_check_timer:
            self._health_check_timer.stop()

        self._health_check_timer = QTimer(self)
        self._health_check_timer.timeout.connect(self._check_browser_health)
        self._health_check_timer.start(HEALTH_CHECK_INTERVAL_MS)

    def _check_browser_health(self) -> None:
        if self.is_closing or not self.session or self._recovering:
            return

        try:
            driver = self.session.driver
            with self.session.lock:
                driver.execute_script("return 1")
        except WebDriverException:
            self._attempt_recovery()

    def _attempt_recovery(self) -> None:
        self._recovering = True
        self._recovery_count += 1
        self.log_message.emit(
            f"Trình duyệt không phản hồi — đang tự động khôi phục (lần {self._recovery_count})..."
        )
        self.status_changed.emit("Đang khôi phục", "#f0b84f")

        if self._health_check_timer:
            self._health_check_timer.stop()

        self.stop_browser()
        self.session = None
        self.browser_thread = None
        self.navigation_thread = None

        self.placeholder_text_changed.emit("Đang khôi phục trình duyệt...")
        self.placeholder_visibility_changed.emit(True)

        self.browser_thread = threading.Thread(
            target=self._recovery_worker,
            daemon=True,
        )
        self.browser_thread.start()

    def _recovery_worker(self) -> None:
        try:
            session = create_browser_session()
        except Exception as e:
            logger.exception("Không khôi phục được trình duyệt")
            self.log_message.emit(f"Khôi phục thất bại: {e} — sẽ thử lại sau 60 giây")
            self.status_changed.emit("Lỗi khôi phục", "#ff6b6b")
            self._recovering = False
            self.start_health_check()
            return

        self._recovering = False
        self._browser_ready.emit(session)

    def start_resource_monitor(self) -> None:
        if self._resource_timer:
            self._resource_timer.stop()

        self._resource_timer = QTimer(self)
        self._resource_timer.timeout.connect(self._check_resources)
        self._resource_timer.start(RESOURCE_CHECK_INTERVAL_MS)

    def _check_resources(self) -> None:
        if self.is_closing or not self.session:
            self.resource_update.emit(0.0, 0.0)
            return

        try:
            driver_pid = self.session.driver.service.process.pid
            proc = psutil.Process(driver_pid)
            cpu = proc.cpu_percent(interval=0.1)
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            self.resource_update.emit(round(cpu, 1), round(rss_mb, 1))

            if rss_mb > MEMORY_WARNING_MB:
                self.log_message.emit(
                    f"Cảnh báo: Chrome đang dùng {rss_mb:.0f} MB RAM (> {MEMORY_WARNING_MB} MB)"
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied, WebDriverException, OSError):
            self.resource_update.emit(0.0, 0.0)

    def show_external_login_prompt(
        self,
        status_text: str,
        message: str,
        url: str | None = None,
    ) -> None:
        if url:
            self.external_login_url = url

        self.external_login_visibility_changed.emit(True)
        self.status_changed.emit(status_text, "#ffb86c")
        self.log_message.emit(message)

    def resize_browser(self, width: int, height: int) -> None:
        if self.is_closing or not self.session or not self.session.hwnd:
            return

        try:
            resize_embedded_window(self.session.hwnd, width, height)
        except Exception:
            logger.debug("Không đổi được kích thước trình duyệt đã nhúng", exc_info=True)

    def focus_browser(
        self,
        active_window: bool,
        visible: bool,
        minimized: bool,
    ) -> None:
        if self.is_closing or minimized or not visible or not active_window:
            return

        if self.session and self.session.hwnd:
            focus_embedded_window(self.session.hwnd)

    def stop_timers(self) -> None:
        for attr in (
            "resize_timer", "taskbar_flash_timer",
            "_health_check_timer", "_resource_timer",
        ):
            timer = getattr(self, attr, None)
            if timer:
                timer.stop()
                setattr(self, attr, None)

    def pause_window_timers(self) -> None:
        if self.resize_timer:
            self.resize_timer.stop()

    def resume_window_timers(self) -> None:
        if not self.session or self.is_closing:
            return

        self.start_resize_timer()
        QTimer.singleShot(100, lambda: self.browser_resize_requested.emit())

    def _on_startup_failed(self, message: str) -> None:
        self.startup_failed.emit(message)
        self.placeholder_text_changed.emit("Không khởi động được trình duyệt")
        self.placeholder_visibility_changed.emit(True)
        self.status_changed.emit("Lỗi khởi động", "#ff6b6b")
        self.log_message.emit(f"Lỗi khởi động trình duyệt: {message}")

    def stop_browser(self) -> None:
        try:
            session = self.session

            if session and session.hwnd:
                release_embedded_window(session.hwnd)

            if session and session.driver:
                self._kill_chrome_process(session)

            self.session = None
        except Exception as e:
            logger.exception("Không đóng được trình duyệt")
            self.log_message.emit(f"Lỗi khi đóng trình duyệt: {e}")

    @staticmethod
    def _kill_chrome_process(session: BrowserSession) -> None:
        try:
            driver_pid = session.driver.service.process.pid
        except Exception:
            logger.debug("Không lấy được PID của ChromeDriver", exc_info=True)
            try:
                session.driver.quit()
            except Exception:
                pass
            return

        for pid in get_process_tree_pids(driver_pid):
            try:
                psutil.Process(pid).kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def open_external_login(self) -> None:
        self.log_message.emit(f"Mở Chrome thật để đăng nhập: {self.external_login_url}")
        self.status_changed.emit("Đăng nhập ngoài", "#60a5fa")
        self.log_message.emit("Đang mở Chrome thật bằng hồ sơ trình duyệt của ứng dụng...")
        self.placeholder_text_changed.emit(
            "Đăng nhập trong cửa sổ Chrome bên ngoài.\n"
            "Sau khi đăng nhập xong, đóng Chrome ngoài rồi chạy lại ứng dụng."
        )
        self.placeholder_visibility_changed.emit(True)
        self.stop_browser()

        try:
            launch_external_chrome(self.external_login_url)
            self.log_message.emit(
                "Đã mở Chrome thật bằng hồ sơ trình duyệt của ứng dụng. "
                "Sau khi đăng nhập xong, đóng Chrome ngoài rồi chạy lại ứng dụng."
            )
        except Exception as e:
            logger.exception("Không mở được Chrome thật để đăng nhập ngoài")
            self.status_changed.emit("Lỗi mở Chrome ngoài", "#ff6b6b")
            self.log_message.emit(f"Không mở được Chrome ngoài: {e}")

    def shutdown(self) -> None:
        self.is_closing = True

        if self.taskbar_flash_timer:
            self.taskbar_flash_timer.stop()
            self.taskbar_flash_timer = None
        if self.resize_timer:
            self.resize_timer.stop()
            self.resize_timer = None
        if self._health_check_timer:
            self._health_check_timer.stop()
            self._health_check_timer = None
        if self._resource_timer:
            self._resource_timer.stop()
            self._resource_timer = None

        self.stop_browser()

        for thread in (self.browser_thread, self.navigation_thread):
            if thread and thread.is_alive():
                thread.join(timeout=5.0)
