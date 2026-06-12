"""
logging_config.py
-----------------
Sets up rotating file + console logging for the entire application.

Log files rotate at 10 MB and keep 7 backups.
A single call to setup_logging() is made at app startup.
"""

import logging
import logging.handlers
from pathlib import Path


def setup_logging(log_dir: Path, log_level: str = "INFO") -> None:
    """
    Configure root logger with:
      - RotatingFileHandler  → D:\\Storage\\Logs\\app.log
      - StreamHandler        → stdout (useful when running under a process manager)
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    level = getattr(logging, log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — 10 MB per file, keep 7 backups
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
