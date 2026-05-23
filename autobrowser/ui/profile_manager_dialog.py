"""Profile manager dialog – create, delete, and switch Chrome profiles."""

import re
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from autobrowser.browser.profile_manager import (
    create_profile,
    delete_profile,
    load_store,
    set_active_profile,
)

_ID_RE = re.compile(r"[^a-z0-9_-]")


class ProfileManagerDialog(QDialog):
    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._data_dir = data_dir
        self._store = load_store(data_dir)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        self.setWindowTitle("Quản lý Profile")
        self.resize(480, 360)
        self.setStyleSheet("""
            QDialog { background: #1a1e29; }
            QLabel { color: #d7dde8; }
            QListWidget {
                background: #10131b;
                color: #d7dde8;
                border: 1px solid #303846;
                border-radius: 3px;
            }
            QListWidget::item { padding: 8px; }
            QListWidget::item:selected {
                background: #263044;
                color: white;
            }
            QPushButton {
                background: #263044;
                color: #d7dde8;
                border: none;
                border-radius: 3px;
                padding: 6px 14px;
            }
            QPushButton:hover { background: #374766; }
        """)

        layout = QVBoxLayout(self)

        title = QLabel("Danh sách profile Chrome")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        hint = QLabel("Mỗi profile là một bộ nhận dạng trình duyệt riêng biệt.")
        hint.setStyleSheet("color: #6b7385; font-size: 11px; margin-bottom: 4px;")
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(200)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()

        new_btn = QPushButton("+ Tạo mới")
        new_btn.clicked.connect(self._create_profile)
        btn_layout.addWidget(new_btn)

        self.switch_btn = QPushButton("✓ Dùng profile này")
        self.switch_btn.clicked.connect(self._switch_profile)
        btn_layout.addWidget(self.switch_btn)

        self.delete_btn = QPushButton("🗑 Xóa")
        self.delete_btn.clicked.connect(self._delete_profile)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background: #5a1a1a; color: #e8a0a0;
                border: none; border-radius: 3px; padding: 6px 14px;
            }
            QPushButton:hover { background: #7a2222; color: #ffb0b0; }
        """)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self.note_label = QLabel("Đổi profile cần khởi động lại ứng dụng.")
        self.note_label.setStyleSheet("color: #6b7385; font-size: 11px; font-style: italic;")
        layout.addWidget(self.note_label)

    def _populate(self) -> None:
        self.list_widget.clear()
        for p in self._store.profiles:
            label = f"{p.name}  [{p.id}]"
            if p.id == self._store.active_id:
                label = f"● {label}  ← đang dùng"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, p.id)
            if p.id == self._store.active_id:
                item.setForeground(Qt.green)
            self.list_widget.addItem(item)

    def _create_profile(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Tạo Profile mới", "Tên hiển thị:",
        )
        if not ok or not name.strip():
            return

        profile_id = _ID_RE.sub("", name.lower().replace(" ", "_"))[:30]
        if not profile_id:
            profile_id = f"profile_{len(self._store.profiles) + 1}"

        profile = create_profile(self._data_dir, name.strip(), profile_id)
        if profile is None:
            QMessageBox.warning(self, "Lỗi", f"Profile ID '{profile_id}' đã tồn tại.")
            return

        self._store = load_store(self._data_dir)
        self._populate()
        QMessageBox.information(
            self, "Đã tạo",
            f"Profile '{name}' đã được tạo.\n"
            "Khởi động lại ứng dụng để dùng profile mới.",
        )

    def _switch_profile(self) -> None:
        current = self.list_widget.currentItem()
        if not current:
            return
        profile_id = current.data(Qt.UserRole)
        if profile_id == self._store.active_id:
            return

        set_active_profile(self._data_dir, profile_id)
        self._store = load_store(self._data_dir)
        self._populate()
        QMessageBox.information(
            self, "Đã chuyển",
            "Profile đã được chuyển đổi.\n"
            "Vui lòng khởi động lại ứng dụng.",
        )

    def _delete_profile(self) -> None:
        current = self.list_widget.currentItem()
        if not current:
            return
        profile_id = current.data(Qt.UserRole)

        if len(self._store.profiles) <= 1:
            QMessageBox.warning(self, "Không thể xóa", "Phải có ít nhất một profile.")
            return

        reply = QMessageBox.question(
            self, "Xóa profile",
            f"Xóa profile '{profile_id}' và toàn bộ dữ liệu Chrome của nó?\n"
            "Hành động này không thể hoàn tác.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        delete_profile(self._data_dir, profile_id)
        self._store = load_store(self._data_dir)
        self._populate()
