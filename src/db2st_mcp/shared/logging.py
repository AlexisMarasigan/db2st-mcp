"""Structured logging via structlog. One configure call at startup."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from db2st_mcp.shared.config import get_settings


def configure_logging() -> None:
    """Configure structlog + stdlib logging. Idempotent."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper())

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound logger pre-populated with common keys."""
    log: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    if initial:
        log = log.bind(**initial)
    return log
