#!/usr/bin/env python3

"""Central logging configuration for the Freesound browser.

A rotating file handler always captures DEBUG detail so problems can be
diagnosed after the fact; the console mirrors messages at the level set via
the ``FREESOUND_LOG_LEVEL`` environment variable (default ``INFO``).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

LOGGER_NAME = "resolve_freesound_browser"

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"

_configured = False


def setup_logging(log_dir: Path) -> logging.Logger:
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    if _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    formatter = logging.Formatter(_LOG_FORMAT)

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        file_target: Path | None = log_dir / "app.log"
    except OSError as exc:  # e.g. read-only home; keep console logging alive
        file_target = None
        logger.warning("Could not open log file in %s: %s", log_dir, exc)

    console_level = os.environ.get("FREESOUND_LOG_LEVEL", "INFO").upper()
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(getattr(logging, console_level, logging.INFO))
    console.setFormatter(formatter)
    logger.addHandler(console)

    _configured = True
    logger.info(
        "Logging initialised (console=%s, file=%s)",
        console_level,
        file_target,
    )
    return logger


def install_excepthook(logger: logging.Logger) -> None:
    """Route otherwise-uncaught exceptions to the log instead of stderr only."""

    def hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = hook
