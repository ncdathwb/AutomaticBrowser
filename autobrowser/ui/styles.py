PLACEHOLDER_PREPARING = "Đang chuẩn bị trình duyệt..."
LOG_TOGGLE_EXPANDED = "Nhật ký ▲"
LOG_TOGGLE_COLLAPSED = "Nhật ký ▼"
EXTERNAL_LOGIN_TEXT = "Đăng nhập ngoài"
INITIAL_STATUS_TEXT = "Đang khởi động"
INITIAL_STATUS_COLOR = "#f0b84f"

CHROME_FRAME_STYLE = """
    QFrame {
        background: #05070b;
        border: none;
    }
"""

PLACEHOLDER_LABEL_STYLE = "color: #d7dde8; font-size: 16px;"

LOG_PANEL_STYLE = """
    QFrame#logDrawer {
        background: #151923;
        border-top: 1px solid #303846;
        border-left: none;
        border-right: none;
        border-bottom: none;
        border-radius: 0;
    }
"""

SPLITTER_HANDLE_STYLE = """
    QSplitter::handle:vertical {
        background: #263044;
        height: 1px;
        margin: 0 8px;
    }
    QSplitter::handle:vertical:hover {
        background: #3b5998;
    }
"""

LOG_TOGGLE_BUTTON_STYLE = """
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
"""

LOG_COPY_BUTTON_STYLE = """
    QPushButton {
        background: #263044;
        color: #a8b2c4;
        border: none;
        border-radius: 3px;
        font-size: 12px;
        padding: 0;
    }
    QPushButton:hover {
        background: #374766;
        color: white;
    }
"""

EXTERNAL_LOGIN_BUTTON_STYLE = """
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
"""

LOG_TEXT_STYLE = """
    QTextEdit {
        background: #10131b;
        color: #8df0b6;
        font-family: Consolas, monospace;
        font-size: 12px;
        border: 1px solid #263044;
        border-radius: 3px;
    }
"""


def status_text(text: str) -> str:
    return f"● {text}"


def status_label_style(color: str) -> str:
    return f"color: {color}; font-weight: bold;"
