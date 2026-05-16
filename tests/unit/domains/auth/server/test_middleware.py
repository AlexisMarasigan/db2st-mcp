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


def test_auth_failure_message_is_identical_for_missing_and_invalid() -> None:
    """Pins the no-error-message-side-channel invariant from
    docs/AUTH.md threat model: an attacker enumerating tokens
    must not be able to tell 'no header' from 'wrong token' by
    reading the response body."""
    store = InMemoryTokenStore()
    client = TestClient(_app(store))

    missing = client.get("/protected").json()
    wrong = client.get("/protected", headers={"Authorization": "Bearer nope"}).json()
    revoked_marker = client.get(
        "/protected", headers={"Authorization": "Bearer "}
    ).json()  # empty token: extract succeeds, lookup fails

    assert missing["error"] == wrong["error"] == revoked_marker["error"] == "unauthorized"
    assert missing["message"] == wrong["message"] == revoked_marker["message"]


def test_auth_failure_logs_distinguish_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire response stays generic, but the internal log line MUST
    carry a distinct `reason` so ops dashboards can split 401s by
    cause. Pairs with the message-identicality test above: outside
    the trust boundary the three branches look the same; inside,
    they don't.

    Patches the middleware module's bound logger directly because
    structlog caches its processor chain at first use, which makes
    `caplog`-based assertions order-dependent across the suite.
    """
    from db2st_mcp.domains.auth.server import middleware as mw

    calls: list[tuple[str, dict[str, object]]] = []

    class _SpyLogger:
        def info(self, event: str, **kw: object) -> None:
            calls.append((event, kw))

    monkeypatch.setattr(mw, "_log", _SpyLogger())

    store = InMemoryTokenStore()
    client = TestClient(_app(store))
    client.get("/protected")  # missing
    client.get("/protected", headers={"Authorization": "Bearer nope"})  # unknown

    reasons = {kw.get("reason") for event, kw in calls if event == "auth.failure"}
    assert "header_missing_or_malformed" in reasons
    assert "token_unknown" in reasons


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


@pytest.mark.asyncio
async def test_middleware_binds_token_id_to_contextvars() -> None:
    """On successful auth, the middleware binds `token_id` and `plan` to
    structlog's contextvars so downstream log lines are correlated.

    Regression: iter 29 found that `request_id_middleware` was reading
    `request.state.auth` *before* this middleware had populated it,
    silently dropping `token_id` from every log line. The binding now
    lives here, where it runs after authenticate succeeds.
    """
    import structlog
    from starlette.applications import Starlette
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.routing import Route

    store = InMemoryTokenStore()
    record, secret = await store.mint(plan="pro", daily_limit=10)

    async def echo_contextvars(request):  # type: ignore[no-untyped-def]
        return JSONResponse(dict(structlog.contextvars.get_contextvars()))

    app = Starlette(routes=[Route("/echo", echo_contextvars)])
    app.add_middleware(BaseHTTPMiddleware, dispatch=bearer_auth_middleware(store))

    client = TestClient(app)
    response = client.get("/echo", headers={"Authorization": f"Bearer {secret}"})

    assert response.status_code == 200
    ctx = response.json()
    assert ctx["token_id"] == record.id
    assert ctx["plan"] == "pro"
