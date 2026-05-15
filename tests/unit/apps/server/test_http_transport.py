"""Integration test for the FastAPI app — the production HTTP deployment path.

Verifies the streamable-HTTP MCP transport is mounted, auth middleware is
wired, and `/healthz` bypasses auth. The MCP transport itself is exercised
end-to-end by `tests/e2e/test_mcp_stdio.py`; here we only confirm the HTTP
plumbing.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from db2st_mcp.apps.server.main import build_app


@pytest.fixture
def fresh_app() -> FastAPI:
    """A new FastAPI app per test.

    The MCP session manager is single-use per instance, so each test gets a
    fresh `build_app()` rather than sharing the module-level singleton.
    """
    return build_app()


def test_healthz_is_public(fresh_app: FastAPI) -> None:
    with TestClient(fresh_app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mcp_endpoint_requires_auth(fresh_app: FastAPI) -> None:
    # No bearer → 401 from the auth middleware before the transport sees the request.
    with TestClient(fresh_app) as client:
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "test", "version": "0.0.1"},
                },
            },
            headers={"accept": "application/json, text/event-stream"},
        )
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "unauthorized"


@pytest.mark.asyncio
async def test_authenticated_request_passes_middleware_to_transport(
    fresh_app: FastAPI,
) -> None:
    """Mint a token, then send a /mcp/ request and verify auth allowed the
    request through. The MCP transport's DNS-rebinding protection rejects
    Host=testserver with 421 — that 421 is in fact proof the auth layer
    accepted us and forwarded to the transport. A 401 here would indicate
    the auth wiring is broken.
    """
    store = fresh_app.state.deps.token_store
    _, secret = await store.mint(plan="pro", daily_limit=10)

    with TestClient(fresh_app) as client:
        response = client.post(
            "/mcp/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "test", "version": "0.0.1"},
                },
            },
            headers={
                "accept": "application/json, text/event-stream",
                "authorization": f"Bearer {secret}",
            },
        )
    # 421 = transport rejected the Host header (production-correct DNS
    # rebinding protection); 4xx/5xx other than 401 also confirms auth
    # let us pass. End-to-end transport behaviour is in
    # tests/e2e/test_mcp_stdio.py.
    assert response.status_code != 401
    assert response.status_code in {200, 202, 400, 421}
