import sys
import time
import threading

from PyQt5.QtCore import QEvent, QEasingCurve, QPropertyAnimation, Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_config import APP_CONFIG
from browser_logic import (
    BrowserSession,
    create_browser_session,
    get_current_url,
    has_google_login_session,
    is_google_captcha_url,
    is_google_login_rejected_url,
    launch_external_chrome_for_login,
    run_browser_logic,
)
from win32_window import (
    embed_window,
    focus_embedded_window,
    release_embedded_window,
    resize_embedded_window,
)


class AppSignals(QObject):
    log = pyqtSignal(str)
    browser_ready = pyqtSignal(object)
    navigation_finished = pyqtSignal(str)
    browser_state_checked = pyqtSignal(object, str, object)
    startup_failed = pyqtSignal(str)


class AutoBrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.session: BrowserSession | None = None
        self.browser_thread: threading.Thread | None = None
        self.navigation_thread: threading.Thread | None = None
        self.browser_state_thread: threading.Thread | None = None
        self.resize_timer: QTimer | None = None
        self.url_monitor_timer: QTimer | None = None
        self.log_animation: QPropertyAnimation | None = None
        self.log_layout: QVBoxLayout | None = None
        self.log_drawer_expanded = True
        self.google_login_rejection_seen = False
        self.is_closing = False
        self.signals = AppSignals()

        self.connect_signals()
        self.init_ui()
        QTimer.singleShot(0, self.start_browser)

    def connect_signals(self):
        self.signals.log.connect(self.append_log)
        self.signals.browser_ready.connect(self.on_browser_ready)
        self.signals.navigation_finished.connect(self.on_navigation_finished)
        self.signals.browser_state_checked.connect(self.on_browser_state_checked)
        self.signals.startup_failed.connect(self.on_startup_failed)

    def init_ui(self):
        self.setWindowTitle(APP_CONFIG.title)
        self.setMinimumSize(APP_CONFIG.min_width, APP_CONFIG.min_height)
        self.resize(APP_CONFIG.width, APP_CONFIG.height)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.chrome_frame = QFrame()
        self.chrome_frame.setFocusPolicy(Qt.StrongFocus)
        self.chrome_frame.mousePressEvent = self.on_browser_frame_clicked
        self.chrome_frame.setMinimumHeight(APP_CONFIG.chrome_frame_min_height)
        self.chrome_frame.setStyleSheet("""
            QFrame {
                background: white;
                border: none;
            }
        """)

        placeholder_layout = QVBoxLayout(self.chrome_frame)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)
        self.placeholder_label = QLabel("Đang chuẩn bị browser...")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet("color: #888; font-size: 16px;")
        self.placeholder_label.setFont(QFont("Arial", 14))
        placeholder_layout.addWidget(self.placeholder_label)

        main_layout.addWidget(self.chrome_frame, stretch=1)

        self.log_panel = QFrame()
        self.log_panel.setObjectName("logDrawer")
        self.log_panel.setMinimumHeight(APP_CONFIG.log_drawer_collapsed_height)
        self.log_panel.setMaximumHeight(APP_CONFIG.log_drawer_expanded_height)
        self.log_panel.setStyleSheet("""
            QFrame#logDrawer {
                background: #151923;
                border-top: 1px solid #303846;
                border-left: none;
                border-right: none;
                border-bottom: none;
                border-radius: 0;
            }
        """)

        log_layout = QVBoxLayout(self.log_panel)
        self.log_layout = log_layout
        log_layout.setSpacing(4)
        log_layout.setContentsMargins(8, 6, 8, 8)

        log_header = QHBoxLayout()
        self.log_toggle_button = QPushButton("Nhật ký ▲")
        self.log_toggle_button.setFocusPolicy(Qt.NoFocus)
        self.log_toggle_button.setFixedHeight(28)
        self.log_toggle_button.clicked.connect(self.toggle_log_drawer)
        self.log_toggle_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #d7dde8;
                border: none;
                font-weight: bold;
                text-align: left;
                padding: 0 4px;
            }
            QPushButton:hover {
                color: white;
            }
        """)
        self.external_login_button = QPushButton("Đăng nhập ngoài")
        self.external_login_button.setFocusPolicy(Qt.NoFocus)
        self.external_login_button.setFixedHeight(28)
        self.external_login_button.clicked.connect(self.open_external_login)
        self.external_login_button.hide()
        self.external_login_button.setStyleSheet("""
            QPushButton {
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 3px;
                font-weight: bold;
                padding: 0 10px;
            }
            QPushButton:hover {
                background: #1d4ed8;
            }
        """)
        self.status_label = QLabel("● Đang khởi động")
        self.status_label.setStyleSheet("color: #f0b84f; font-weight: bold;")
        log_header.addWidget(self.log_toggle_button)
        log_header.addStretch()
        log_header.addWidget(self.external_login_button)
        log_header.addWidget(self.status_label)
        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFocusPolicy(Qt.NoFocus)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background: #10131b;
                color: #8df0b6;
                font-family: Consolas, monospace;
                font-size: 12px;
                border: 1px solid #263044;
                border-radius: 3px;
            }
        """)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(self.log_panel)

    def start_browser(self):
        if self.browser_thread and self.browser_thread.is_alive():
            return

        self.placeholder_label.setText("Đang khởi động browser...")
        self.set_status("Đang khởi động", "#f0b84f")
        self.log("Đang khởi động browser...")

        self.browser_thread = threading.Thread(
            target=self.create_browser_worker,
            daemon=True,
        )
        self.browser_thread.start()

    def create_browser_worker(self):
        try:
            session = create_browser_session()
            self.signals.browser_ready.emit(session)
        except Exception as e:
            self.signals.startup_failed.emit(str(e))

    def on_browser_ready(self, session: BrowserSession):
        if self.is_closing:
            with session.lock:
                session.driver.quit()
            return

        self.session = session

        if not session.hwnd:
            self.placeholder_label.setText("Chrome đang chạy nhưng chưa nhúng được vào GUI")
            self.set_status("Lỗi nhúng", "#ff6b6b")
            self.log("❌ Không tìm thấy HWND Chrome.")
            return

        self.embed_browser(session.hwnd)
        self.start_navigation()

    def embed_browser(self, hwnd: int):
        try:
            parent_hwnd = int(self.chrome_frame.winId())
            self.placeholder_label.hide()
            embed_window(hwnd, parent_hwnd)
            self.resize_browser()
            self.focus_browser()
            QTimer.singleShot(250, self.resize_browser)
            QTimer.singleShot(300, self.focus_browser)
            QTimer.singleShot(750, self.resize_browser)
            QTimer.singleShot(800, self.focus_browser)
            QTimer.singleShot(1500, self.focus_browser)
            self.start_resize_timer()
            self.start_url_monitor()
            self.set_status("Connected", "#5ee089")
            self.log("Browser đã sẵn sàng.")
        except Exception as e:
            self.set_status("Lỗi", "#ff6b6b")
            self.log(f"❌ Lỗi khi nhúng Chrome: {e}")

    def start_navigation(self):
        if not self.session:
            return

        self.navigation_thread = threading.Thread(
            target=self.navigate_worker,
            daemon=True,
        )
        self.navigation_thread.start()

    def navigate_worker(self):
        try:
            if self.is_closing or not self.session:
                return
            current_url = run_browser_logic(self.session)
            self.signals.navigation_finished.emit(current_url)
        except Exception as e:
            self.signals.log.emit(f"❌ Lỗi điều hướng browser: {e}")

    def on_navigation_finished(self, current_url: str):
        self.log(f"✅ Đã mở: {current_url}")
        self.resize_browser()
        self.focus_browser()
        QTimer.singleShot(300, self.resize_browser)
        QTimer.singleShot(350, self.focus_browser)
        QTimer.singleShot(1000, self.focus_browser)

        if is_google_captcha_url(current_url):
            self.log(
                "⚠️ Google đang yêu cầu CAPTCHA vì phát hiện Chrome/Selenium. "
                "App không thể tự động vượt CAPTCHA."
            )

        if is_google_login_rejected_url(current_url):
            self.handle_google_login_rejected()
            return

        QTimer.singleShot(800, self.start_browser_state_check)
        QTimer.singleShot(2500, self.start_browser_state_check)

    def start_resize_timer(self):
        if self.resize_timer:
            self.resize_timer.stop()

        self.resize_timer = QTimer()
        self.resize_timer.timeout.connect(self.resize_browser)
        self.resize_timer.start(APP_CONFIG.resize_interval_ms)

    def start_url_monitor(self):
        if self.url_monitor_timer:
            self.url_monitor_timer.stop()

        self.url_monitor_timer = QTimer()
        self.url_monitor_timer.timeout.connect(self.start_browser_state_check)
        self.url_monitor_timer.start(1500)

    def start_browser_state_check(self):
        if (
            self.is_closing
            or self.isMinimized()
            or not self.isVisible()
            or not self.session
            or not self.session.driver
        ):
            return

        if self.browser_state_thread and self.browser_state_thread.is_alive():
            return

        session = self.session
        self.browser_state_thread = threading.Thread(
            target=self.browser_state_worker,
            args=(session,),
            daemon=True,
        )
        self.browser_state_thread.start()

    def browser_state_worker(self, session: BrowserSession):
        current_url = ""
        is_logged_in = None

        try:
            if self.is_closing or session is not self.session:
                return

            current_url = get_current_url(session)
            if not is_google_login_rejected_url(current_url):
                is_logged_in = has_google_login_session(session)
        except Exception:
            return

        self.signals.browser_state_checked.emit(session, current_url, is_logged_in)

    def on_browser_state_checked(
        self,
        session: BrowserSession,
        current_url: str,
        is_logged_in: bool | None,
    ):
        if self.is_closing or session is not self.session:
            return

        if is_google_login_rejected_url(current_url):
            self.handle_google_login_rejected()
            return

        if is_logged_in is not None and not self.google_login_rejection_seen:
            self.external_login_button.setVisible(not is_logged_in)

    def handle_google_login_rejected(self):
        if self.google_login_rejection_seen:
            return

        self.google_login_rejection_seen = True
        self.external_login_button.show()
        self.set_status("Google chặn đăng nhập", "#ffb86c")
        self.log(
            "⚠️ Google không cho đăng nhập trong Chrome đang chạy bằng Selenium. "
            "Hãy bấm 'Đăng nhập ngoài' để đăng nhập bằng Chrome thật."
        )

    def update_external_login_button(self):
        if self.google_login_rejection_seen:
            return

        self.start_browser_state_check()

    def resize_browser(self):
        if (
            self.is_closing
            or self.isMinimized()
            or not self.isVisible()
            or not self.session
            or not self.session.hwnd
        ):
            return

        try:
            rect = self.chrome_frame.rect()
            resize_embedded_window(
                self.session.hwnd,
                rect.width(),
                rect.height(),
            )
        except Exception:
            pass

    def on_startup_failed(self, message: str):
        self.placeholder_label.setText("Không khởi động được browser")
        self.set_status("Lỗi khởi động", "#ff6b6b")
        self.log(f"❌ Lỗi khởi động browser: {message}")

    def stop_browser(self):
        try:
            if self.resize_timer:
                self.resize_timer.stop()
                self.resize_timer = None

            if self.url_monitor_timer:
                self.url_monitor_timer.stop()
                self.url_monitor_timer = None

            session = self.session

            if session and session.hwnd:
                release_embedded_window(session.hwnd)

            if session and session.driver:
                with session.lock:
                    session.driver.quit()

            self.session = None
        except Exception as e:
            self.log(f"❌ Lỗi khi đóng browser: {e}")

    def append_log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")

    def log(self, msg: str):
        self.append_log(msg)

    def on_browser_frame_clicked(self, event):
        self.focus_browser()
        event.accept()

    def focus_browser(self):
        if self.is_closing or self.isMinimized() or not self.isVisible():
            return

        if not self.isActiveWindow():
            return

        if self.session and self.session.hwnd:
            focus_embedded_window(self.session.hwnd)

    def changeEvent(self, event):
        super().changeEvent(event)

        if event.type() != QEvent.WindowStateChange:
            return

        if self.isMinimized():
            if self.resize_timer:
                self.resize_timer.stop()
            if self.url_monitor_timer:
                self.url_monitor_timer.stop()
            return

        if self.session and not self.is_closing:
            self.start_resize_timer()
            self.start_url_monitor()
            QTimer.singleShot(100, self.resize_browser)

    def set_status(self, text: str, color: str):
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def open_external_login(self):
        self.set_status("Đăng nhập ngoài", "#60a5fa")
        self.log("Đang mở Chrome thật để đăng nhập Google...")
        self.placeholder_label.setText(
            "Đăng nhập trong cửa sổ Chrome bên ngoài.\n"
            "Sau khi đăng nhập xong, đóng Chrome ngoài rồi chạy lại app."
        )
        self.placeholder_label.show()
        self.stop_browser()

        try:
            launch_external_chrome_for_login()
            self.log(
                "Đã mở Chrome thật bằng profile của project. "
                "Sau khi đăng nhập xong, đóng Chrome ngoài rồi chạy lại app."
            )
        except Exception as e:
            self.set_status("Lỗi mở Chrome ngoài", "#ff6b6b")
            self.log(f"❌ Không mở được Chrome ngoài: {e}")

    def toggle_log_drawer(self):
        expanding = not self.log_drawer_expanded
        target_height = (
            APP_CONFIG.log_drawer_expanded_height
            if expanding
            else APP_CONFIG.log_drawer_collapsed_height
        )
        self.log_drawer_expanded = expanding
        self.log_toggle_button.setText(
            "Nhật ký ▲" if self.log_drawer_expanded else "Nhật ký ▼"
        )

        if self.log_layout:
            if expanding:
                self.log_layout.setSpacing(4)
                self.log_layout.setContentsMargins(8, 6, 8, 8)
                self.log_text.show()
            else:
                self.log_text.hide()
                self.log_layout.setSpacing(0)
                self.log_layout.setContentsMargins(8, 0, 8, 0)

        self.log_animation = QPropertyAnimation(self.log_panel, b"maximumHeight")
        self.log_animation.setDuration(APP_CONFIG.log_drawer_animation_ms)
        self.log_animation.setStartValue(self.log_panel.maximumHeight())
        self.log_animation.setEndValue(target_height)
        self.log_animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.log_animation.start()

    def closeEvent(self, event):
        self.is_closing = True
        self.stop_browser()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = AutoBrowserWindow()
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
