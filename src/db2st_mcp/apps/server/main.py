"""FastAPI ASGI app. Sprint 0 stub; sprint 1 wires the real MCP transport."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI

from db2st_mcp.shared.logging import configure_logging, get_logger

configure_logging()
_log = get_logger(__name__)


def build_app() -> FastAPI:
    """Construct the FastAPI ASGI app."""
    app = FastAPI(title="db2st-mcp", version="0.0.1")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    _log.info("app.built")
    return app


app: Final[FastAPI] = build_app()
