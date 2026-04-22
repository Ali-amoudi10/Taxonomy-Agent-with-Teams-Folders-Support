from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

from app.runtime_paths import local_app_data_dir

_LOG_LOCK = threading.Lock()
_LOGGING_CONFIGURED = False
_LOG_FILE_NAME = "taxonomy_agent.log"


def _log_directory() -> Path:
    path = local_app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file_path() -> Path:
    return _log_directory() / _LOG_FILE_NAME


def _desired_level() -> int:
    level_name = os.getenv("APP_LOG_LEVEL", "INFO").upper().strip()
    return getattr(logging, level_name, logging.INFO)


def _safe_stream_handler() -> logging.Handler:
    stream = sys.stdout if getattr(sys, "stdout", None) is not None else sys.stderr
    handler = logging.StreamHandler(stream)
    handler.setLevel(_desired_level())
    return handler


def configure_logging() -> Path:
    global _LOGGING_CONFIGURED

    with _LOG_LOCK:
        log_path = log_file_path()
        root = logging.getLogger()
        level = _desired_level()

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )

        if not _LOGGING_CONFIGURED:
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=2 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)

            stream_handler = _safe_stream_handler()
            stream_handler.setFormatter(formatter)
            root.addHandler(stream_handler)

            root.setLevel(level)
            _LOGGING_CONFIGURED = True
        else:
            root.setLevel(level)
            for handler in root.handlers:
                handler.setLevel(level)
                handler.setFormatter(formatter)

        return log_path


def get_logger(name: str = "pptx_slide_finder") -> logging.Logger:
    configure_logging()
    logger = logging.getLogger(name)
    logger.setLevel(_desired_level())
    return logger
