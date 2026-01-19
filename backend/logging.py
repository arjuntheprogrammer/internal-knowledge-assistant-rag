import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def configure_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    if _is_production():
        if not _has_stdout_handler(root_logger):
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(formatter)
            root_logger.addHandler(stream_handler)
    else:
        log_dir = os.path.join(os.getcwd(), "backend", "logs")
        os.makedirs(log_dir, exist_ok=True)
        if _has_log_dir_handler(root_logger, log_dir):
            return

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


def _is_production():
    return os.getenv("FLASK_CONFIG") == "production" or os.getenv("K_SERVICE")


def _has_stdout_handler(logger):
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and getattr(
            handler, "stream", None
        ) in (sys.stdout, sys.stderr):
            return True
    return False


def _has_log_dir_handler(logger, log_dir):
    for handler in logger.handlers:
        filename = getattr(handler, "baseFilename", "")
        if filename and os.path.commonpath([filename, log_dir]) == log_dir:
            return True
    return False
