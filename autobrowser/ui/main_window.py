import logging
import threading
import time

from PyQt5.QtCore import QEvent, QFileInfo, Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from autobrowser.config import APP_CONFIG
from autobrowser.controllers.browser_controller import BrowserController
from autobrowser.ui import styles
from autobrowser.ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

LOG_DRAWER_DRAG_MIN_HEIGHT = 150


class AutoBrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = BrowserController()
        self.log_layout: QVBoxLayout | None = None
        self.log_drawer_expanded = True
        self._suppress_splitter_event = False

        self.init_ui()
        self.connect_controller()
        QTimer.singleShot(0, self.start_controller)

    def init_ui(self) -> None:
        self.setWindowTitle(APP_CONFIG.title)
        self._load_chrome_icon()
        self.setMinimumSize(APP_CONFIG.min_width, APP_CONFIG.min_height)
        self.resize(APP_CONFIG.width, APP_CONFIG.height)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        self.splitter.setStyleSheet(styles.SPLITTER_HANDLE_STYLE)
        self.splitter.splitterMoved.connect(self.on_splitter_moved)

        self.chrome_frame = QFrame()
        self.chrome_frame.setFocusPolicy(Qt.StrongFocus)
        self.chrome_frame.mousePressEvent = self.on_browser_frame_clicked
        self.chrome_frame.setMinimumHeight(150)
        self.chrome_frame.setStyleSheet(styles.CHROME_FRAME_STYLE)

        placeholder_layout = QVBoxLayout(self.chrome_frame)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)
        self.placeholder_label = QLabel(styles.PLACEHOLDER_PREPARING)
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet(styles.PLACEHOLDER_LABEL_STYLE)
        self.placeholder_label.setFont(QFont("Arial", 14))
        placeholder_layout.addWidget(self.placeholder_label)

        self.splitter.addWidget(self.chrome_frame)
        self.create_log_drawer(self.splitter)

        total = APP_CONFIG.height
        chrome_h = total - APP_CONFIG.log_drawer_expanded_height
        self.splitter.setSizes([chrome_h, APP_CONFIG.log_drawer_expanded_height])

        main_layout.addWidget(self.splitter, stretch=1)

    def _load_chrome_icon(self) -> None:
        from autobrowser.browser.external_chrome import find_chrome_executable

        chrome_path = find_chrome_executable()
        if chrome_path and chrome_path.is_file():
            provider = QFileIconProvider()
            self.setWindowIcon(provider.icon(QFileInfo(str(chrome_path))))

    def create_log_drawer(self, splitter: QSplitter) -> None:
        self.log_panel = QFrame()
        self.log_panel.setObjectName("logDrawer")
        self.log_panel.setMinimumHeight(APP_CONFIG.log_drawer_collapsed_height)
        self.log_panel.setStyleSheet(styles.LOG_PANEL_STYLE)

        log_layout = QVBoxLayout(self.log_panel)
        self.log_layout = log_layout
        log_layout.setSpacing(4)
        log_layout.setContentsMargins(8, 6, 8, 8)

        log_header = QHBoxLayout()
        self.log_toggle_button = QPushButton(styles.LOG_TOGGLE_EXPANDED)
        self.log_toggle_button.setFocusPolicy(Qt.NoFocus)
        self.log_toggle_button.setFixedHeight(28)
        self.log_toggle_button.clicked.connect(self.toggle_log_drawer)
        self.log_toggle_button.setStyleSheet(styles.LOG_TOGGLE_BUTTON_STYLE)

        self.log_copy_button = QPushButton("⧉")
        self.log_copy_button.setFocusPolicy(Qt.NoFocus)
        self.log_copy_button.setFixedSize(24, 22)
        self.log_copy_button.setToolTip("Sao chép toàn bộ nội dung nhật ký")
        self.log_copy_button.clicked.connect(self.copy_log_to_clipboard)
        self.log_copy_button.setStyleSheet(styles.LOG_COPY_BUTTON_STYLE)

        self.settings_button = QPushButton("⚙")
        self.settings_button.setFocusPolicy(Qt.NoFocus)
        self.settings_button.setFixedSize(24, 22)
        self.settings_button.setToolTip("Cài đặt profile")
        self.settings_button.clicked.connect(self.open_settings)
        self.settings_button.setStyleSheet(styles.LOG_COPY_BUTTON_STYLE)

        self.external_login_button = QPushButton(styles.EXTERNAL_LOGIN_TEXT)
        self.external_login_button.setFocusPolicy(Qt.NoFocus)
        self.external_login_button.setFixedHeight(28)
        self.external_login_button.clicked.connect(self.controller.open_external_login)
        self.external_login_button.hide()
        self.external_login_button.setStyleSheet(styles.EXTERNAL_LOGIN_BUTTON_STYLE)

        self.status_label = QLabel(styles.status_text(styles.INITIAL_STATUS_TEXT))
        self.status_label.setStyleSheet(styles.status_label_style(styles.INITIAL_STATUS_COLOR))

        self.resource_label = QLabel("")
        self.resource_label.setStyleSheet(styles.RESOURCE_LABEL_STYLE)

        log_header.addWidget(self.log_toggle_button)
        log_header.addWidget(self.log_copy_button)
        log_header.addWidget(self.settings_button)
        log_header.addStretch()
        log_header.addWidget(self.resource_label)
        log_header.addWidget(self.external_login_button)
        log_header.addWidget(self.status_label)
        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFocusPolicy(Qt.NoFocus)
        self.log_text.setStyleSheet(styles.LOG_TEXT_STYLE)
        log_layout.addWidget(self.log_text)
        splitter.addWidget(self.log_panel)

    def connect_controller(self) -> None:
        self.controller.log_message.connect(self.append_log)
        self.controller.status_changed.connect(self.set_status)
        self.controller.placeholder_text_changed.connect(self.placeholder_label.setText)
        self.controller.placeholder_visibility_changed.connect(self.placeholder_label.setVisible)
        self.controller.external_login_visibility_changed.connect(
            self.external_login_button.setVisible
        )
        self.controller.resource_update.connect(self.set_resource_info)
        self.controller.browser_embed_requested.connect(self.embed_browser)
        self.controller.browser_resize_requested.connect(self.resize_browser_to_frame)

    def start_controller(self) -> None:
        self.controller.start(int(self.winId()))

    def embed_browser(self, child_hwnd: int) -> None:
        rect = self.chrome_frame.rect()
        self.controller.embed_browser(
            child_hwnd=child_hwnd,
            parent_hwnd=int(self.chrome_frame.winId()),
            width=rect.width(),
            height=rect.height(),
        )

    def resize_browser_to_frame(self) -> None:
        if self.isMinimized() or not self.isVisible():
            return

        rect = self.chrome_frame.rect()
        self.controller.resize_browser(rect.width(), rect.height())

    def append_log(self, msg: str) -> None:
        logger.info(msg)
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")

    def copy_log_to_clipboard(self) -> None:
        text = self.log_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.log_copy_button.setText("✓")
            QTimer.singleShot(1200, lambda: self.log_copy_button.setText("⧉"))

    def open_settings(self) -> None:
        dialog = SettingsDialog(APP_CONFIG.data_dir, self)
        dialog.exec_()

    def on_browser_frame_clicked(self, event) -> None:
        self.controller.focus_browser(
            active_window=self.isActiveWindow(),
            visible=self.isVisible(),
            minimized=self.isMinimized(),
        )
        event.accept()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)

        if event.type() != QEvent.WindowStateChange:
            return

        if self.isMinimized():
            self.controller.pause_window_timers()
            return

        self.controller.resume_window_timers()

    def set_resource_info(self, cpu: float, rss_mb: float) -> None:
        if cpu == 0.0 and rss_mb == 0.0:
            self.resource_label.setText("")
            return
        self.resource_label.setText(
            f"CPU {cpu:.0f}%  |  RAM {rss_mb:.0f} MB"
        )

    def set_status(self, text: str, color: str) -> None:
        self.status_label.setText(styles.status_text(text))
        self.status_label.setStyleSheet(styles.status_label_style(color))

    def toggle_log_drawer(self) -> None:
        expanding = not self.log_drawer_expanded
        self.log_drawer_expanded = expanding
        self.log_toggle_button.setText(
            styles.LOG_TOGGLE_EXPANDED if self.log_drawer_expanded else styles.LOG_TOGGLE_COLLAPSED
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

        total = self.splitter.height()
        if expanding:
            log_h = APP_CONFIG.log_drawer_expanded_height
        else:
            log_h = APP_CONFIG.log_drawer_collapsed_height
        chrome_h = total - log_h - self.splitter.handleWidth()
        self._suppress_splitter_event = True
        self.splitter.setSizes([chrome_h, log_h])
        self._suppress_splitter_event = False

    def on_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._suppress_splitter_event:
            return

        sizes = self.splitter.sizes()
        if len(sizes) < 2:
            return
        log_h = sizes[1]
        drag_min = LOG_DRAWER_DRAG_MIN_HEIGHT

        if log_h < drag_min:
            self._suppress_splitter_event = True
            total = self.splitter.height()
            chrome_h = total - drag_min - self.splitter.handleWidth()
            self.splitter.setSizes([chrome_h, drag_min])
            self._suppress_splitter_event = False
            return

        expanded = log_h > APP_CONFIG.log_drawer_collapsed_height + 10
        if expanded == self.log_drawer_expanded:
            return

        self.log_drawer_expanded = expanded
        self.log_toggle_button.setText(
            styles.LOG_TOGGLE_EXPANDED if self.log_drawer_expanded else styles.LOG_TOGGLE_COLLAPSED
        )

        if self.log_layout:
            if expanded:
                self.log_layout.setSpacing(4)
                self.log_layout.setContentsMargins(8, 6, 8, 8)
                self.log_text.show()
            else:
                self.log_text.hide()
                self.log_layout.setSpacing(0)
                self.log_layout.setContentsMargins(8, 0, 8, 0)

    def closeEvent(self, event) -> None:
        event.accept()
        self.hide()
        self.controller.stop_timers()
        shutdown_thread = threading.Thread(
            target=self.controller.shutdown,
            daemon=False,
        )
        shutdown_thread.start()
        shutdown_thread.join(timeout=8.0)
