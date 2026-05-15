"""FastAPI ASGI app — composes the MCP transport, auth middleware, and health.

Module-level `app` is exported for ASGI servers:
    uvicorn db2st_mcp.apps.server.main:app
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

import structlog
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from db2st_mcp.apps.server.dependencies import AppDeps, build_deps
from db2st_mcp.apps.server.mcp_app import build_mcp_server
from db2st_mcp.apps.server.middleware import request_id_middleware
from db2st_mcp.domains.auth.server.middleware import bearer_auth_middleware
from db2st_mcp.shared.config import get_settings
from db2st_mcp.shared.logging import configure_logging
from db2st_mcp.shared.observability import instrument_app

configure_logging()
_log = structlog.get_logger(__name__)


def _auth_disabled() -> bool:
    return os.getenv("DB2ST_AUTH_DISABLED", "").lower() in {"1", "true", "yes"}


def build_app() -> FastAPI:
    """Construct the FastAPI ASGI app with MCP + auth + health routes."""
    settings = get_settings()
    deps = build_deps(settings)
    mcp = build_mcp_server(deps.tracking_service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _log.info("app.starting", token_store=type(deps.token_store).__name__)
        try:
            yield
        finally:
            await deps.aclose()
            _log.info("app.stopped")

    app = FastAPI(title="db2st-mcp", version="0.0.1", lifespan=lifespan)
    app.state.deps = deps

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Auth middleware (added before mount so it wraps the MCP transport).
    if _auth_disabled():
        _log.warning("app.auth_disabled")
    else:
        app.add_middleware(
            BaseHTTPMiddleware,
            dispatch=bearer_auth_middleware(deps.token_store),
        )
        _log.info("app.auth_enabled")

    # Request-id correlation runs last → executes first per Starlette ordering.
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_id_middleware)

    app.mount("/mcp", mcp.streamable_http_app())
    instrument_app(app)
    _log.info("app.built")
    return app


app: Final[FastAPI] = build_app()


# Expose deps for tests / scripts that import the module.
__all__ = ["AppDeps", "app", "build_app"]
