"""Request-correlation middleware. Binds a request id + token id to the
structlog context so every log line in a request is correlatable.
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
    token_id = getattr(request.state, "auth", None)
    bind: dict[str, object] = {"request_id": request_id, "path": request.url.path}
    if token_id is not None:
        bind["token_id"] = token_id.token_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**bind)
    try:
        response = await call_next(request)
    except Exception:
        _log.exception("request.failed")
        raise
    response.headers["x-request-id"] = request_id
    return response
