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
from db2st_mcp.shared.upstash_cache import CacheCodec

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

    cache: _Cache | None = _build_cache(settings)
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


# B105 (hardcoded-password-string): "upstash" is a backend enum literal,
# not a credential.
def _build_cache(settings: Settings) -> _Cache:
    """Pick the response-cache backend. `memory` is per-pod (lost on
    restart); `upstash` is shared across pods and survives churn."""
    ttl = float(settings.response_cache_ttl_seconds)
    if settings.response_cache_backend == "upstash":  # nosec B105
        from db2st_mcp.shared.upstash_cache import UpstashCache

        codec: CacheCodec[Shipment] = CacheCodec(
            encode=lambda s: s.model_dump_json(),
            decode=Shipment.model_validate_json,
        )
        _log.info(
            "deps.response_cache.upstash",
            ttl_seconds=settings.response_cache_ttl_seconds,
        )
        return UpstashCache.from_settings(
            settings,
            codec=codec,
            key_prefix="db2st:shipment",
        )
    return TTLCache[Shipment](maxsize=512, ttl_seconds=ttl)
