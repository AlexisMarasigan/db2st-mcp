"""Bearer-token auth middleware.

Validates `Authorization: Bearer <secret>`, consumes one quota unit on
success, and stamps `request.state.auth` with an `AuthContext` for
downstream code. `/healthz`, `/docs`, and `/openapi.json` bypass.

Wired into the FastAPI app by `db2st_mcp.apps.server.main.build_app`.
Disable for development with `DB2ST_AUTH_DISABLED=1`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from db2st_mcp.domains.auth.shared import AuthContext, TokenStore
from db2st_mcp.shared.errors import QuotaExceededError, UnauthorizedError

_log = structlog.get_logger(__name__)

# Single generic message for every auth-failure branch so the response
# body does not leak whether the header was absent vs. the token was
# wrong vs. the token was revoked. See docs/AUTH.md threat model
# (Error-message side channel row).
_AUTH_FAILURE_MSG = "missing or invalid bearer token"


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        # Logged with a distinct `reason` so ops dashboards can split
        # 401s by cause (header missing vs. token wrong vs. token
        # revoked). The response stays generic; the log line never
        # leaves the trust boundary.
        _log.info("auth.failure", reason="header_missing_or_malformed")
        raise UnauthorizedError(_AUTH_FAILURE_MSG)
    return header[len("Bearer ") :].strip()


async def authenticate(
    request: Request,
    store: TokenStore,
) -> AuthContext:
    """Validate the request's bearer token and decrement quota.

    Quota is decremented up-front by `consume`. Failed downstream calls
    therefore burn a quota unit; this is documented in `docs/AUTH.md` as
    an accepted trade-off (refund-on-failure is a future enhancement).
    """
    secret = _extract_bearer(request)
    record = await store.lookup(secret)
    if record is None:
        _log.info("auth.failure", reason="token_unknown")
        raise UnauthorizedError(_AUTH_FAILURE_MSG)
    if record.revoked_at is not None:
        _log.info("auth.failure", reason="token_revoked", token_id=record.id)
        raise UnauthorizedError(_AUTH_FAILURE_MSG)
    outcome = await store.consume(record.id, datetime.now(UTC).date())
    if outcome == "exhausted":
        _log.info("auth.quota_exhausted", token_id=record.id, plan=record.plan)
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
        # Bind the token id to the structlog context so downstream log
        # lines in this request can be correlated to the caller.
        structlog.contextvars.bind_contextvars(token_id=ctx.token_id, plan=ctx.plan)
        return await call_next(request)

    return middleware
