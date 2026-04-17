"""Structlog configuration used across the pipeline.

A single call to ``configure()`` at CLI entry is sufficient. All modules should
obtain loggers via ``structlog.get_logger(__name__)``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def configure(log_level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure structlog for CLI and library use.

    Parameters
    ----------
    log_level:
        Standard logging level name (DEBUG, INFO, WARNING, ERROR).
    log_file:
        Optional path to a JSONL log file. If given, a second handler writes
        machine-readable events there in addition to human-readable stderr.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(format="%(message)s", level=level, handlers=handlers)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
