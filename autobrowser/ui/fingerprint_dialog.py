"""Fingerprint history dashboard – displays saved fingerprint snapshots over time."""

import json
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def _load_fingerprints(data_dir: Path) -> list[dict]:
    """Load all fingerprint snapshots sorted by timestamp (oldest first)."""
    fp_dir = data_dir / "fingerprints"
    if not fp_dir.is_dir():
        return []

    results: list[dict] = []
    for fpath in sorted(fp_dir.glob("fp_*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            data["_file"] = fpath.name
            results.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return results


def _short_hash(hash_str: str) -> str:
    if not hash_str or hash_str in ("lỗi", "N/A", "timeout"):
        return hash_str[:12] if hash_str else "—"
    return hash_str[:8] + "…"


def _same_hash(a: str, b: str) -> bool:
    return bool(a and b and a == b)


class FingerprintDialog(QDialog):
    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self._data_dir = data_dir
        self._fingerprints = _load_fingerprints(data_dir)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        self.setWindowTitle("Fingerprint History")
        self.resize(1100, 600)
        self.setStyleSheet("""
            QDialog { background: #1a1e29; }
            QLabel { color: #d7dde8; }
            QTableWidget {
                background: #10131b;
                color: #d7dde8;
                gridline-color: #263044;
                border: 1px solid #303846;
                font-size: 11px;
            }
            QTableWidget::item { padding: 4px 6px; }
            QHeaderView::section {
                background: #263044;
                color: #a8b2c4;
                border: none;
                padding: 4px 6px;
                font-weight: bold;
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

        # Summary header
        summary_layout = QHBoxLayout()
        self.summary_label = QLabel("Đang tải dữ liệu fingerprint...")
        self.summary_label.setStyleSheet("color: #8df0b6; font-size: 12px;")
        summary_layout.addWidget(self.summary_label)
        summary_layout.addStretch()

        refresh_btn = QPushButton("⟳ Làm mới")
        refresh_btn.clicked.connect(self._refresh)
        summary_layout.addWidget(refresh_btn)

        layout.addLayout(summary_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Thời gian", "Canvas Hash", "Audio Hash",
            "WebGL Renderer", "WebRTC IPs", "External IP",
            "WebDriver", "Fonts", "Cảnh báo",
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

    def _refresh(self) -> None:
        self._fingerprints = _load_fingerprints(self._data_dir)
        self._populate()

    def _populate(self) -> None:
        if not self._fingerprints:
            self.summary_label.setText("Chưa có dữ liệu fingerprint. Chạy ứng dụng để thu thập.")
            self.summary_label.setStyleSheet("color: #6b7385; font-size: 12px;")
            self.table.setRowCount(0)
            return

        self.table.setRowCount(len(self._fingerprints))

        prev_info: dict | None = None
        for row, fp in enumerate(self._fingerprints):
            info = fp.get("info", fp) if isinstance(fp.get("info"), dict) else {}
            self._fill_row(row, fp, info, prev_info)
            prev_info = info

        # Summary
        latest = self._fingerprints[-1]
        latest_info = latest.get("info", {})
        canvas = _short_hash(str(latest_info.get("canvasHash", "—")))
        audio = _short_hash(str(latest.get("audioHash", latest_info.get("audioHash", "—"))))
        wd = "CÓ" if latest_info.get("webdriver") else "không"
        self.summary_label.setText(
            f"Lần cuối: {latest.get('timestamp', '?')}  |  "
            f"Canvas: {canvas}  |  Audio: {audio}  |  "
            f"WebDriver: {wd}  |  Tổng: {len(self._fingerprints)} bản ghi"
        )
        self.summary_label.setStyleSheet("color: #8df0b6; font-size: 12px;")

    def _fill_row(
        self,
        row: int,
        fp: dict,
        info: dict,
        prev_info: dict | None,
    ) -> None:
        ts = fp.get("timestamp", "?")
        canvas = str(info.get("canvasHash", "—"))
        audio = str(fp.get("audioHash", info.get("audioHash", "—")))
        webgl = str(info.get("webglRenderer", "—"))
        webrtc = str(fp.get("webrtcIps", info.get("webrtcIps", "—")))
        ext_ip = str(fp.get("externalIp", info.get("externalIp", "—")))
        webdriver = "CÓ" if info.get("webdriver") else "không"
        fonts = _font_summary(str(info.get("fonts", "—")))

        # Detect changes vs previous
        flags: list[str] = []
        if prev_info:
            prev_canvas = str(prev_info.get("canvasHash", ""))
            if prev_canvas and prev_canvas != canvas and canvas != "lỗi":
                flags.append("Canvas thay đổi!")

        self._set_cell(row, 0, ts)
        self._set_cell(row, 1, _short_hash(canvas),
                       changed=bool(flags and "Canvas" in flags[0]))
        self._set_cell(row, 2, _short_hash(audio))
        self._set_cell(row, 3, webgl[:60] if len(webgl) > 60 else webgl)
        self._set_cell(row, 4, webrtc)
        self._set_cell(row, 5, ext_ip)
        self._set_cell(row, 6, webdriver,
                       warn=(webdriver == "CÓ"))
        self._set_cell(row, 7, fonts)
        self._set_cell(row, 8, "; ".join(flags) if flags else "—",
                       warn=bool(flags))

    def _set_cell(
        self,
        row: int,
        col: int,
        text: str,
        changed: bool = False,
        warn: bool = False,
    ) -> None:
        item = QTableWidgetItem(text)
        if warn:
            item.setForeground(QColor("#ff6b6b"))
            item.setFont(QFont("", -1, QFont.Bold))
        elif changed:
            item.setForeground(QColor("#f0b84f"))
        self.table.setItem(row, col, item)


def _font_summary(fonts_str: str) -> str:
    if fonts_str in ("—", "lỗi", "N/A", ""):
        return fonts_str
    parts = fonts_str.split(":")
    if len(parts) >= 2:
        try:
            count_part = parts[0]
            return f"{count_part} fonts"
        except (ValueError, IndexError):
            pass
    return fonts_str[:40]
