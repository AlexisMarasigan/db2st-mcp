"""Unit tests for `request_id_middleware`.

Verifies:
- A missing `x-request-id` is generated (UUIDv4 shape).
- A caller-supplied `x-request-id` is preserved and echoed back.
- The response always carries the header.
- `path` is bound to the structlog contextvars.
- When auth middleware is composed in the chain, its `token_id` lands
  on the same contextvars (separate concern, owned by the auth
  middleware itself — see `test_middleware_binds_token_id_to_contextvars`
  in tests/unit/domains/auth/server/test_middleware.py).
"""

from __future__ import annotations

import re

import pytest
import structlog
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from db2st_mcp.apps.server.middleware import request_id_middleware

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@pytest.fixture
def app() -> Starlette:
    async def echo(request):  # type: ignore[no-untyped-def]
        ctx = structlog.contextvars.get_contextvars()
        return JSONResponse({"context": dict(ctx)})

    app = Starlette(routes=[Route("/echo", echo)])
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)
    return app


def test_missing_header_is_generated_as_uuid(app: Starlette) -> None:
    with TestClient(app) as client:
        response = client.get("/echo")
    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    assert UUID_RE.match(request_id), f"not a uuid: {request_id}"


def test_caller_supplied_header_is_preserved(app: Starlette) -> None:
    with TestClient(app) as client:
        response = client.get("/echo", headers={"x-request-id": "trace-12345"})
    assert response.headers["x-request-id"] == "trace-12345"


def test_path_is_bound_to_contextvars(app: Starlette) -> None:
    with TestClient(app) as client:
        response = client.get("/echo")
    ctx = response.json()["context"]
    assert ctx["path"] == "/echo"
    assert "request_id" in ctx


def test_request_id_does_not_touch_token_id(app: Starlette) -> None:
    """The token id is not the request-id middleware's concern.

    request_id_middleware is added last → runs first → has no view of
    `state.auth`. token_id binding lives in the auth middleware
    instead; this test pins that the request-id middleware doesn't
    accidentally bind a stale or empty token_id.
    """
    with TestClient(app) as client:
        response = client.get("/echo")
    ctx = response.json()["context"]
    assert "token_id" not in ctx


def test_route_exception_propagates_via_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """A route exception travels through the middleware's
    `except Exception: _log.exception; raise` branch. The exception
    propagates to Starlette's exception middleware (HTTP 500); the
    captured log call records the `request.failed` event so an SRE
    can correlate by request_id.
    """
    from db2st_mcp.apps.server import middleware as rim_module
    from tests.conftest import SpyLogger

    spy = SpyLogger()
    monkeypatch.setattr(rim_module, "_log", spy)

    async def boom(_request):  # type: ignore[no-untyped-def]
        msg = "synthetic explosion"
        raise RuntimeError(msg)

    app = Starlette(routes=[Route("/boom", boom)])
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    # Without this assertion, removing the `_log.exception(...)` line
    # leaves the test green -- the original test only checked the 500
    # status, not that the exception was actually logged.
    events = [event for event, _ in spy.calls]
    assert "request.failed" in events
