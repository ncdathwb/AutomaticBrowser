import logging
from logging.handlers import RotatingFileHandler

from autobrowser.config import APP_CONFIG, AppConfig

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3


def configure_logging(config: AppConfig = APP_CONFIG) -> None:
    config.log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level, logging.INFO))

    for handler in list(root_logger.handlers):
        if getattr(handler, "_autobrowser_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    file_handler = RotatingFileHandler(
        config.log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    file_handler.setLevel(getattr(logging, config.log_level, logging.INFO))
    file_handler._autobrowser_handler = True

    root_logger.addHandler(file_handler)
    logging.captureWarnings(True)
