import logging
import threading
import time

from PyQt5.QtCore import QEvent, QFileInfo, Qt, QTimer
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QSystemTrayIcon,
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
        self._log_entries: list[tuple[str, str]] = []  # (level, message)

        self._quit_requested = False
        self.tray_icon: QSystemTrayIcon | None = None

        self.init_ui()
        self._setup_tray()
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
        chrome_path = self._find_chrome_path()
        if chrome_path and chrome_path.is_file():
            provider = QFileIconProvider()
            self.setWindowIcon(provider.icon(QFileInfo(str(chrome_path))))

    @staticmethod
    def _find_chrome_path():
        from autobrowser.browser.external_chrome import find_chrome_executable

        return find_chrome_executable()

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

        self.log_filter_combo = QComboBox()
        self.log_filter_combo.addItems(["ALL", "INFO", "WARNING", "ERROR"])
        self.log_filter_combo.setCurrentText("ALL")
        self.log_filter_combo.setFocusPolicy(Qt.NoFocus)
        self.log_filter_combo.setFixedWidth(90)
        self.log_filter_combo.setStyleSheet(styles.FILTER_COMBO_STYLE)
        self.log_filter_combo.currentTextChanged.connect(self._apply_log_filter)

        self.auto_scroll_check = QCheckBox("↓")
        self.auto_scroll_check.setFocusPolicy(Qt.NoFocus)
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.setToolTip("Tự động cuộn xuống dòng mới nhất")
        self.auto_scroll_check.setStyleSheet(styles.FILTER_COMBO_STYLE)

        self.fingerprint_button = QPushButton("FP")
        self.fingerprint_button.setFocusPolicy(Qt.NoFocus)
        self.fingerprint_button.setFixedSize(28, 22)
        self.fingerprint_button.setToolTip("Lịch sử fingerprint")
        self.fingerprint_button.clicked.connect(self.open_fingerprint_dashboard)
        self.fingerprint_button.setStyleSheet(styles.LOG_COPY_BUTTON_STYLE)

        self.profile_button = QPushButton("👤")
        self.profile_button.setFocusPolicy(Qt.NoFocus)
        self.profile_button.setFixedSize(28, 22)
        self.profile_button.setToolTip("Quản lý profile")
        self.profile_button.clicked.connect(self.open_profile_manager)
        self.profile_button.setStyleSheet(styles.LOG_COPY_BUTTON_STYLE)

        log_header.addWidget(self.log_toggle_button)
        log_header.addWidget(self.log_copy_button)
        log_header.addWidget(self.settings_button)
        log_header.addWidget(self.fingerprint_button)
        log_header.addWidget(self.profile_button)
        log_header.addStretch()
        log_header.addWidget(self.auto_scroll_check)
        log_header.addWidget(self.log_filter_combo)
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

    @staticmethod
    def _detect_level(msg: str) -> str:
        lower = msg.lower()
        if any(kw in lower for kw in ("lỗi", "error", "thất bại", "không thể", "crash")):
            return "ERROR"
        if any(kw in lower for kw in ("cảnh báo", "warning", "rủi ro", "phát hiện")):
            return "WARNING"
        return "INFO"

    def append_log(self, msg: str) -> None:
        level = self._detect_level(msg)
        logger.info(msg)
        self._log_entries.append((level, msg))

        if not self._level_visible(level):
            return

        timestamp = time.strftime("%H:%M:%S")
        prefix = {"ERROR": "  ✕  ", "WARNING": "  ⚠  ", "INFO": "  ●  "}.get(level, "  ●  ")
        color = {"ERROR": "#ff6b6b", "WARNING": "#f0b84f", "INFO": "#8df0b6"}.get(level, "#8df0b6")
        self.log_text.append(
            f'<span style="color:#6b7385">[{timestamp}]</span>'
            f'<span style="color:{color}">{prefix}{msg}</span>'
        )

        if self.auto_scroll_check.isChecked():
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _level_visible(self, level: str) -> bool:
        filt = self.log_filter_combo.currentText()
        if filt == "ALL":
            return True
        return level == filt

    def _apply_log_filter(self) -> None:
        self._rebuild_log_display()

    def _rebuild_log_display(self) -> None:
        self.log_text.clear()
        for level, msg in self._log_entries:
            if not self._level_visible(level):
                continue
            timestamp = time.strftime("%H:%M:%S")
            prefix = {"ERROR": "  ✕  ", "WARNING": "  ⚠  ", "INFO": "  ●  "}.get(level, "  ●  ")
            color = {"ERROR": "#ff6b6b", "WARNING": "#f0b84f", "INFO": "#8df0b6"}.get(level, "#8df0b6")
            self.log_text.append(
                f'<span style="color:#6b7385">[{timestamp}]</span>'
                f'<span style="color:{color}">{prefix}{msg}</span>'
            )
        if self.auto_scroll_check.isChecked():
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def open_fingerprint_dashboard(self) -> None:
        from autobrowser.ui.fingerprint_dialog import FingerprintDialog

        dialog = FingerprintDialog(APP_CONFIG.data_dir, self)
        dialog.exec_()

    def copy_log_to_clipboard(self) -> None:
        text = self.log_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.log_copy_button.setText("✓")
            QTimer.singleShot(1200, lambda: self.log_copy_button.setText("⧉"))

    def open_settings(self) -> None:
        dialog = SettingsDialog(APP_CONFIG.data_dir, self)
        dialog.exec_()

    def open_profile_manager(self) -> None:
        from autobrowser.ui.profile_manager_dialog import ProfileManagerDialog

        dialog = ProfileManagerDialog(APP_CONFIG.data_dir, self)
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

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        icon = self.windowIcon()
        if icon.isNull():
            icon = QApplication.style().standardIcon(
                QApplication.style().SP_ComputerIcon
            )

        tray_menu = QMenu()
        restore_action = QAction("Hiện cửa sổ", tray_menu)
        restore_action.triggered.connect(self._restore_from_tray)
        tray_menu.addAction(restore_action)

        tray_menu.addSeparator()

        exit_action = QAction("Thoát", tray_menu)
        exit_action.triggered.connect(self._quit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip(APP_CONFIG.title)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: int) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self) -> None:
        self._quit_requested = True
        if self.tray_icon:
            self.tray_icon.hide()
        self.close()

    def closeEvent(self, event) -> None:
        if self.tray_icon and self.tray_icon.isVisible() and not self._quit_requested:
            self.hide()
            self.tray_icon.showMessage(
                APP_CONFIG.title,
                "Ứng dụng vẫn đang chạy trong khay hệ thống.\n"
                "Nhấp đúp để mở lại, hoặc chuột phải → Thoát.",
                QSystemTrayIcon.Information,
                3000,
            )
            event.ignore()
            return

        event.accept()
        self.hide()
        self.controller.stop_timers()
        shutdown_thread = threading.Thread(
            target=self.controller.shutdown,
            daemon=True,
        )
        shutdown_thread.start()
        shutdown_thread.join(timeout=8.0)
