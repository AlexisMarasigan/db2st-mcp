"""Request-correlation middleware. Binds a request id to the structlog
context so every log line in a request is correlatable. The token id is
bound separately by the auth middleware after the bearer is validated —
this middleware runs outermost (added last; Starlette is LIFO) so
`request.state.auth` is always None at this point.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.requests import Request
from starlette.responses import Response

_log = structlog.get_logger(__name__)


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        _log.exception("request.failed")
        raise
    response.headers["x-request-id"] = request_id
    return response
