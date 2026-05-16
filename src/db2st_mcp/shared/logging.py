"""Structured logging via structlog. One configure call at startup.

Modules get their own logger directly:

    import structlog
    _log = structlog.get_logger(__name__)

No wrapper here -- structlog's stdlib factory is enough. Pre-binding
keys at construction is `structlog.get_logger(__name__).bind(...)`.
"""

from __future__ import annotations

import logging
import sys

import structlog

from db2st_mcp.shared.config import get_settings


def configure_logging() -> None:
    """Configure structlog + stdlib logging. Idempotent."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper())

    # Always log to stderr. stdio MCP transport reserves stdout for
    # JSON-RPC frames; ASGI workers (uvicorn) also log to stderr by
    # convention. This keeps stdout consumable for tooling that pipes
    # it (the `stdio` CLI subcommand, `scripts/example_call.py`, etc).
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
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
