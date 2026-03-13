"""
system/logger.py
-----------------
Professional logging setup with rotating file handler.

Usage:
    from system.logger import setup_logger, get_logger

    setup_logger()                    # call once at startup
    log = get_logger(__name__)        # in every module
    log.info("Message")
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from paths import Paths

# Module-level sentinel so setup_logger() is idempotent
_configured = False


def setup_logger(
    level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    console_output: bool = True,
) -> None:
    """
    Configure the root logger once.
    Reads preferred settings from Config if already initialized.
    """
    global _configured
    if _configured:
        return

    # Try to pull settings from Config (non-fatal if not yet initialized)
    try:
        from system.config import Config
        level = Config.get("logging.level", level)
        max_mb = Config.get("logging.max_file_size_mb", max_bytes // (1024 * 1024))
        max_bytes = int(max_mb) * 1024 * 1024
        backup_count = Config.get("logging.backup_count", backup_count)
        console_output = Config.get("logging.console_output", console_output)
    except Exception:
        pass  # Use defaults if Config isn't ready yet

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create logs directory if absent
    log_path = Paths.log()

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Rotating file handler ──────────────────────────────────────────
    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)
    root_logger.addHandler(file_handler)

    # ── Console handler ────────────────────────────────────────────────
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(numeric_level)
        root_logger.addHandler(console_handler)

    _configured = True
    root_logger.info("FileForge logger initialized — log: %s", log_path)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.  Use as:
        log = get_logger(__name__)
    """
    return logging.getLogger(name)
