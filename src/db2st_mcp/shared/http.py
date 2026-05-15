"""HTTP client wrapper with timeout + retry policy.

Domains use this instead of raw httpx so retry/circuit-breaker policy lives in
one place.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from db2st_mcp.shared.config import get_settings


@asynccontextmanager
async def upstream_client(
    *,
    base_url: str | None = None,
    timeout_ms: int | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a configured async HTTP client for upstream calls.

    Caller is responsible for handling httpx.HTTPError; domains translate to
    Db2stError subclasses.
    """
    settings = get_settings()
    timeout_s = (timeout_ms or settings.schenker_timeout_ms) / 1000.0
    async with httpx.AsyncClient(
        base_url=base_url or str(settings.schenker_base_url),
        timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 3.0)),
        headers={"user-agent": "db2st-mcp/0.0.1"},
        follow_redirects=True,
    ) as client:
        yield client
