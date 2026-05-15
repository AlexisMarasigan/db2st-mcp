"""Bearer-token auth middleware (sprint 2 wires it into the app).

Sprint 0 ships the function so it can be unit-tested ahead of integration.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from db2st_mcp.domains.auth.shared import AuthContext, TokenStore
from db2st_mcp.shared.errors import QuotaExceededError, UnauthorizedError


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        raise UnauthorizedError("missing bearer token")
    return header[len("Bearer ") :].strip()


async def authenticate(
    request: Request,
    store: TokenStore,
) -> AuthContext:
    """Validate the request's bearer token and decrement quota.

    Quota is decremented up-front by `consume`. Callers that fail downstream
    can decide whether to refund (sprint 2 enhancement).
    """
    secret = _extract_bearer(request)
    record = await store.lookup(secret)
    if record is None or record.revoked_at is not None:
        raise UnauthorizedError("invalid token")
    outcome = await store.consume(record.id, datetime.now(UTC).date())
    if outcome == "exhausted":
        raise QuotaExceededError("daily quota exceeded", details={"token_id": record.id})
    return AuthContext(token_id=record.id, plan=record.plan, remaining_today=int(outcome))


def bearer_auth_middleware(
    store: TokenStore,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Build a Starlette-style middleware bound to a token store."""

    async def middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Health and docs are unauthenticated.
        if request.url.path in {"/healthz", "/docs", "/openapi.json"}:
            return await call_next(request)
        try:
            ctx = await authenticate(request, store)
        except UnauthorizedError as e:
            return JSONResponse({"error": e.code, "message": e.message}, status_code=e.http_status)
        except QuotaExceededError as e:
            return JSONResponse(
                {"error": e.code, "message": e.message, "details": e.details},
                status_code=e.http_status,
                headers={"retry-after": "86400"},
            )
        request.state.auth = ctx
        return await call_next(request)

    return middleware
