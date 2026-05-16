"""Logging module — `configure_logging` is idempotent."""

from __future__ import annotations

from db2st_mcp.shared.logging import configure_logging


def test_configure_logging_idempotent() -> None:
    configure_logging()
    configure_logging()  # second call must not raise
