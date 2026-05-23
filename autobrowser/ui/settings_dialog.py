from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from autobrowser.proxy_config import ProxyConfig, load_proxy_config, save_proxy_config


class SettingsDialog(QDialog):
    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        self._data_dir = data_dir
        self._config = load_proxy_config(data_dir)
        self._build_ui()
        self._load_config()

    def _build_ui(self) -> None:
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(380)
        self.setStyleSheet("""
            QDialog {
                background: #1a1e29;
            }
            QGroupBox {
                color: #d7dde8;
                font-weight: bold;
                border: 1px solid #303846;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                color: #a8b2c4;
            }
            QLineEdit, QSpinBox, QComboBox {
                background: #10131b;
                color: #d7dde8;
                border: 1px solid #303846;
                border-radius: 3px;
                padding: 3px 6px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #3b5998;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background: #10131b;
                color: #d7dde8;
                selection-background-color: #263044;
            }
            QCheckBox {
                color: #d7dde8;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background: #10131b;
                border: 1px solid #303846;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border-color: #2563eb;
            }
            QDialogButtonBox QPushButton {
                background: #263044;
                color: #d7dde8;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                min-width: 80px;
            }
            QDialogButtonBox QPushButton:hover {
                background: #374766;
            }
            QLabel#hintLabel {
                color: #6b7385;
                font-size: 11px;
                font-style: italic;
            }
        """)

        layout = QVBoxLayout(self)

        proxy_group = QGroupBox("Proxy")
        form = QFormLayout(proxy_group)
        form.setSpacing(8)

        self.enable_check = QCheckBox("Bật proxy")
        self.enable_check.toggled.connect(self._on_enable_toggled)
        form.addRow("", self.enable_check)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["HTTP", "HTTPS", "SOCKS4", "SOCKS5"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        form.addRow("Loại:", self.type_combo)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("vd: 127.0.0.1")
        form.addRow("Host:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8080)
        form.addRow("Port:", self.port_spin)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("(tùy chọn)")
        form.addRow("Username:", self.user_edit)

        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setPlaceholderText("(tùy chọn)")
        form.addRow("Password:", self.pass_edit)

        self.auth_hint = QLabel("SOCKS4 không hỗ trợ xác thực username/password.")
        self.auth_hint.setObjectName("hintLabel")
        self.auth_hint.setWordWrap(True)
        self.auth_hint.hide()
        form.addRow("", self.auth_hint)

        hint = QLabel("Thay đổi proxy cần khởi động lại ứng dụng để có hiệu lực.")
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        layout.addWidget(proxy_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)

        self.delete_button = QPushButton("Xóa cấu hình")
        self.delete_button.setStyleSheet("""
            QPushButton {
                background: #5a1a1a;
                color: #e8a0a0;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #7a2222;
                color: #ffb0b0;
            }
        """)
        self.delete_button.clicked.connect(self._delete_config)
        buttons.addButton(self.delete_button, QDialogButtonBox.DestructiveRole)

        layout.addWidget(buttons)

    def _load_config(self) -> None:
        self.enable_check.setChecked(self._config.enabled)
        type_map = {"http": "HTTP", "https": "HTTPS", "socks4": "SOCKS4", "socks5": "SOCKS5"}
        display_text = type_map.get(self._config.type, "HTTP")
        idx = self.type_combo.findText(display_text)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        self.host_edit.setText(self._config.host)
        self.port_spin.setValue(self._config.port)
        self.user_edit.setText(self._config.username)
        self.pass_edit.setText(self._config.password)
        self._on_enable_toggled(self._config.enabled)

    def _on_enable_toggled(self, checked: bool) -> None:
        for w in (self.type_combo, self.host_edit, self.port_spin):
            w.setEnabled(checked)
        self._update_auth_fields(checked)

    def _on_type_changed(self, text: str) -> None:
        self._update_auth_fields(self.enable_check.isChecked())

    def _update_auth_fields(self, enabled: bool) -> None:
        is_socks4 = self.type_combo.currentText() == "SOCKS4"
        auth_enabled = enabled and not is_socks4
        self.user_edit.setEnabled(auth_enabled)
        self.pass_edit.setEnabled(auth_enabled)
        self.auth_hint.setVisible(enabled and is_socks4)
        if is_socks4 and enabled:
            self.user_edit.setPlaceholderText("(SOCKS4 không hỗ trợ)")
            self.pass_edit.setPlaceholderText("(SOCKS4 không hỗ trợ)")
        else:
            self.user_edit.setPlaceholderText("(tùy chọn)")
            self.pass_edit.setPlaceholderText("(tùy chọn)")

    def _delete_config(self) -> None:
        reply = QMessageBox.question(
            self,
            "Xóa cấu hình proxy",
            "Bạn có chắc muốn xóa toàn bộ cấu hình proxy đã lưu?\n\n"
            "Cần khởi động lại ứng dụng để thay đổi có hiệu lực.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.enable_check.setChecked(False)
        self.type_combo.setCurrentIndex(0)
        self.host_edit.clear()
        self.port_spin.setValue(8080)
        self.user_edit.clear()
        self.pass_edit.clear()

        if not save_proxy_config(ProxyConfig(), self._data_dir):
            QMessageBox.warning(self, "Lỗi", "Không thể ghi file cấu hình proxy.")
            return
        self.accept()

    def _save_and_accept(self) -> None:
        type_map = {"HTTP": "http", "HTTPS": "https", "SOCKS4": "socks4", "SOCKS5": "socks5"}
        proxy_type = type_map.get(self.type_combo.currentText(), "http")
        new_config = ProxyConfig(
            enabled=self.enable_check.isChecked(),
            type=proxy_type,
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.user_edit.text().strip(),
            password=self.pass_edit.text(),
        )

        if new_config.enabled and not new_config.host:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập host của proxy.")
            return

        if not save_proxy_config(new_config, self._data_dir):
            QMessageBox.warning(self, "Lỗi", "Không thể ghi file cấu hình proxy.")
            return
        self.accept()

        if new_config.enabled:
            QMessageBox.information(
                self,
                "Đã lưu proxy",
                "Cấu hình proxy đã được lưu.\n\n"
                "Vui lòng khởi động lại ứng dụng để proxy có hiệu lực.",
            )
        else:
            QMessageBox.information(
                self,
                "Đã lưu",
                "Đã tắt proxy.\n\n"
                "Vui lòng khởi động lại ứng dụng để thay đổi có hiệu lực.",
            )
