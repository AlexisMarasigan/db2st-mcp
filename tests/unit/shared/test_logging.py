"""Logging module — configure + get_logger are idempotent + bindable."""

from __future__ import annotations

from db2st_mcp.shared.logging import configure_logging, get_logger


def test_configure_logging_idempotent() -> None:
    configure_logging()
    configure_logging()  # second call must not raise


def test_get_logger_returns_bound_logger() -> None:
    log = get_logger("test", scope="unit")
    # structlog's BoundLogger exposes .info etc; just smoke-call it.
    log.info("hello", extra="x")
