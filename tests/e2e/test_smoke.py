"""E2E smoke — replaced in iteration 3 by `test_mcp_stdio.py`.

Kept here so the harness has an extra cheap sanity check that the in-process
FastAPI app boots and serves /healthz. The full MCP transport path is
covered by `test_mcp_stdio.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from db2st_mcp.apps.server.main import app

pytestmark = pytest.mark.e2e


def test_healthz_e2e() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
