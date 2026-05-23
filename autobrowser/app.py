import logging
import sys

from PyQt5.QtWidgets import QApplication

from autobrowser.config import APP_CONFIG
from autobrowser.logging_config import configure_logging
from autobrowser.ui.main_window import AutoBrowserWindow

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging(APP_CONFIG)
    logger.info("%s %s đang khởi động", APP_CONFIG.name, APP_CONFIG.version)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = AutoBrowserWindow()
    window.showMaximized()

    sys.exit(app.exec_())
