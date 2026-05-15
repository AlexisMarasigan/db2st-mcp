"""Smoke test: FastAPI app boots and /healthz responds."""

from __future__ import annotations

from fastapi.testclient import TestClient

from db2st_mcp.apps.server.main import app


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
