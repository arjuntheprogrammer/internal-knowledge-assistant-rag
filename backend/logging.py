import logging
import os
from logging.handlers import RotatingFileHandler


def configure_logging():
    log_dir = os.path.join(os.getcwd(), "backend", "logs")
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    if _has_configured_handler(root_logger, log_dir):
        return

    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    info_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)

    error_handler = RotatingFileHandler(
        os.path.join(log_dir, "error.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    root_logger.addHandler(info_handler)
    root_logger.addHandler(error_handler)

    logging.getLogger("werkzeug").setLevel(logging.INFO)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)


def _has_configured_handler(logger, log_dir):
    for handler in logger.handlers:
        filename = getattr(handler, "baseFilename", "")
        if filename and os.path.commonpath([filename, log_dir]) == log_dir:
            return True
    return False
