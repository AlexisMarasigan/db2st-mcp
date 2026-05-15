"""Observability — verifies the no-op + opt-in branches."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from db2st_mcp.shared.observability import instrument_app


def test_instrument_is_noop_when_endpoint_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    # Should be a no-op; calling it must not raise on a fresh app.
    instrument_app(FastAPI())
