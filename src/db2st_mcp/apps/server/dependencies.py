"""Process-wide singletons. Built once at app construction."""

from __future__ import annotations

import os
from dataclasses import dataclass

import structlog

from db2st_mcp.domains.auth.server.store import InMemoryTokenStore
from db2st_mcp.domains.auth.shared import TokenStore
from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient
from db2st_mcp.domains.tracking.server.service import (
    TrackingService,
    _Cache,
    _CircuitBreaker,
    _HtmlFallback,
)
from db2st_mcp.domains.tracking.shared.schemas import Shipment
from db2st_mcp.shared.cache import TTLCache
from db2st_mcp.shared.circuit_breaker import CircuitBreaker
from db2st_mcp.shared.config import Settings

_log = structlog.get_logger(__name__)


@dataclass
class AppDeps:
    """Process-wide dependency bundle. Built once at startup."""

    token_store: TokenStore
    schenker_client: SchenkerClient
    tracking_service: TrackingService

    async def aclose(self) -> None:
        await self.schenker_client.aclose()


def build_deps(settings: Settings) -> AppDeps:
    """Construct dependencies. Synchronous: each dep is lazy-async-init internally."""
    # B105 (hardcoded-password-string): "upstash" is an enum literal
    # for the token-store backend, not a credential.
    if settings.token_store == "upstash":  # nosec B105
        from db2st_mcp.domains.auth.server.upstash_store import UpstashTokenStore

        token_store: TokenStore = UpstashTokenStore.from_settings(settings)
    else:
        token_store = InMemoryTokenStore()

    schenker_client = SchenkerClient()

    cache: _Cache | None = TTLCache[Shipment](maxsize=512, ttl_seconds=60.0)
    breaker: _CircuitBreaker | None = CircuitBreaker(failure_threshold=5, cooldown_seconds=30.0)
    fallback: _HtmlFallback | None = None
    if os.getenv("DB2ST_HTML_FALLBACK", "").lower() in {"1", "true", "yes"}:
        try:
            from db2st_mcp.domains.tracking.server.html_fallback import (
                PlaywrightHtmlFallback,
            )

            fallback = PlaywrightHtmlFallback()
            _log.info("deps.html_fallback_enabled")
        except ImportError:
            _log.warning("deps.html_fallback_unavailable")

    tracking_service = TrackingService(
        schenker_client,
        cache=cache,
        breaker=breaker,
        html_fallback=fallback,
    )

    return AppDeps(
        token_store=token_store,
        schenker_client=schenker_client,
        tracking_service=tracking_service,
    )
