"""E2E smoke. Sprint 0: prove the harness + report generator round-trips.

Sprint 1 will replace these with real MCP-client-against-server scenarios.
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


@pytest.mark.skip(reason="MCP tool not wired yet — sprint 1 implements track_shipment")
def test_track_shipment_against_sample_ref() -> None:
    # Will hit the MCP transport with a Bearer token and call `track_shipment`.
    raise AssertionError("placeholder")
