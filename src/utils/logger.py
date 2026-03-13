"""Centralized logging configuration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.config import get_settings, LOGS_DIR

_initialized = False


def setup_logging() -> logging.Logger:
    """Configure and return the application root logger."""
    global _initialized
    if _initialized:
        return logging.getLogger("ai_pcb")

    settings = get_settings()

    # Ensure log directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = Path(settings.log_file)
    if not log_file.is_absolute():
        log_file = LOGS_DIR / log_file.name

    logger = logging.getLogger("ai_pcb")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File handler
    try:
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        logger.warning("Could not create log file at %s", log_file)

    _initialized = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the ai_pcb namespace."""
    setup_logging()
    if name:
        return logging.getLogger(f"ai_pcb.{name}")
    return logging.getLogger("ai_pcb")
