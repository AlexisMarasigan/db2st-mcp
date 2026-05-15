"""Unit tests for the bearer auth middleware."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from db2st_mcp.domains.auth.server.middleware import (
    _extract_bearer,
    authenticate,
    bearer_auth_middleware,
)
from db2st_mcp.domains.auth.server.store import InMemoryTokenStore
from db2st_mcp.shared.errors import QuotaExceededError, UnauthorizedError


def _app(store: InMemoryTokenStore) -> Starlette:
    async def ok(request):  # type: ignore[no-untyped-def]
        ctx = getattr(request.state, "auth", None)
        return JSONResponse({"token_id": ctx.token_id if ctx else None})

    async def health(request):  # type: ignore[no-untyped-def]
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/protected", ok), Route("/healthz", health)])
    app.add_middleware(BaseHTTPMiddleware, dispatch=bearer_auth_middleware(store))
    return app


def test_extract_bearer_raises_when_missing() -> None:
    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    with pytest.raises(UnauthorizedError):
        _extract_bearer(Request(scope))


def test_health_endpoint_bypasses_auth() -> None:
    store = InMemoryTokenStore()
    client = TestClient(_app(store))
    response = client.get("/healthz")
    assert response.status_code == 200


def test_missing_auth_returns_401() -> None:
    store = InMemoryTokenStore()
    client = TestClient(_app(store))
    response = client.get("/protected")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_invalid_token_returns_401() -> None:
    store = InMemoryTokenStore()
    client = TestClient(_app(store))
    response = client.get("/protected", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_returns_auth_context(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    store = InMemoryTokenStore()
    _, secret = await store.mint(plan="pro", daily_limit=10)

    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/protected",
        "headers": [(b"authorization", f"Bearer {secret}".encode())],
    }
    ctx = await authenticate(Request(scope), store)
    assert ctx.plan == "pro"
    assert ctx.remaining_today == 9


@pytest.mark.asyncio
async def test_authenticate_exhausted_quota_raises() -> None:
    store = InMemoryTokenStore()
    _, secret = await store.mint(plan="free", daily_limit=1)

    from starlette.requests import Request

    headers = [(b"authorization", f"Bearer {secret}".encode())]
    scope = {"type": "http", "method": "GET", "path": "/p", "headers": headers}

    # First call succeeds
    await authenticate(Request(scope), store)
    # Second call → exhausted
    with pytest.raises(QuotaExceededError):
        await authenticate(Request(scope), store)


@pytest.mark.asyncio
async def test_middleware_returns_429_when_exhausted() -> None:
    store = InMemoryTokenStore()
    _, secret = await store.mint(plan="free", daily_limit=1)

    client = TestClient(_app(store))
    first = client.get("/protected", headers={"Authorization": f"Bearer {secret}"})
    assert first.status_code == 200

    second = client.get("/protected", headers={"Authorization": f"Bearer {secret}"})
    assert second.status_code == 429
    assert second.json()["error"] == "quota_exceeded"
    assert second.headers["retry-after"] == "86400"
