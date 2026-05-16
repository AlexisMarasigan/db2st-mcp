"""Tracking service — the orchestration layer that the MCP tool calls.

`get_shipment` is the only public symbol: hides resolver→detail→parse from
the tool. Cache, circuit breaker, and HTML fallback are wrapped here so the
tool itself stays a one-liner.
"""

from __future__ import annotations

from typing import Protocol

import structlog

from db2st_mcp.domains.tracking.server.parser import parse_detail
from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient
from db2st_mcp.domains.tracking.shared.schemas import Shipment
from db2st_mcp.shared.errors import (
    NotFoundError,
    ParseError,
    UpstreamUnavailableError,
)

_log = structlog.get_logger(__name__)


class _Cache(Protocol):
    async def get(self, key: str) -> Shipment | None: ...
    async def set(self, key: str, value: Shipment) -> None: ...


class _CircuitBreaker(Protocol):
    @property
    def open(self) -> bool: ...
    def record_success(self) -> None: ...
    def record_failure(self) -> None: ...


class _HtmlFallback(Protocol):
    async def fetch(self, reference: str) -> Shipment: ...


class TrackingService:
    """Resolve a tracking reference to a `Shipment`.

    Wired with optional cache, circuit breaker, and HTML fallback. Each is
    fail-soft: missing/disabled features degrade gracefully.
    """

    def __init__(
        self,
        client: SchenkerClient,
        *,
        cache: _Cache | None = None,
        breaker: _CircuitBreaker | None = None,
        html_fallback: _HtmlFallback | None = None,
    ) -> None:
        self._client = client
        self._cache = cache
        self._breaker = breaker
        self._fallback = html_fallback

    async def aclose(self) -> None:
        """Release resources owned by the orchestrator's primitives.

        Today only the cache backend may own external connections
        (`UpstashCache` wraps upstash-redis's httpx pool). `TTLCache`
        is in-memory and has no cleanup; both cases handled via
        `getattr(..., None)`.
        """
        aclose = getattr(self._cache, "aclose", None)
        if aclose is not None:
            await aclose()

    async def get_shipment(self, reference: str) -> Shipment:
        ref = reference.strip()
        cached = await self._cache_get(ref)
        if cached is not None:
            _log.info("tracking.cache_hit", reference=ref)
            return cached

        if self._breaker is not None and self._breaker.open:
            return await self._fallback_or_fail(ref, reason="breaker_open")

        try:
            type_hint, upstream_id = await self._client.resolve(ref)
            detail = await self._client.fetch_detail(type_hint, upstream_id)
            shipment = parse_detail(ref, type_hint, detail)
        except NotFoundError:
            if self._breaker is not None:
                self._breaker.record_success()  # 404 is a "fine" upstream response
            raise
        except (UpstreamUnavailableError, ParseError) as e:
            if self._breaker is not None:
                self._breaker.record_failure()
            return await self._fallback_or_fail(ref, reason=e.code)
        else:
            if self._breaker is not None:
                self._breaker.record_success()
            await self._cache_set(ref, shipment)
            return shipment

    async def _cache_get(self, ref: str) -> Shipment | None:
        """Cache read that degrades to a miss on backend failure.

        A `UpstashCache` outage would otherwise propagate through the
        service to the wire. The cache is a latency optimisation, not
        a correctness dependency — treat any read error as a miss and
        let the upstream path fire.
        """
        if self._cache is None:
            return None
        try:
            return await self._cache.get(ref)
        except Exception as e:
            _log.warning(
                "tracking.cache_get_failed",
                reference=ref,
                cause=type(e).__name__,
            )
            return None

    async def _cache_set(self, ref: str, shipment: Shipment) -> None:
        """Cache write that swallows backend failures.

        Mirror of `_cache_get`. We already have the result; failing the
        request because the cache couldn't store it would be a regression
        from the no-cache path.
        """
        if self._cache is None:
            return
        try:
            await self._cache.set(ref, shipment)
        except Exception as e:
            _log.warning(
                "tracking.cache_set_failed",
                reference=ref,
                cause=type(e).__name__,
            )

    async def _fallback_or_fail(self, reference: str, *, reason: str) -> Shipment:
        if self._fallback is None:
            raise UpstreamUnavailableError(
                "primary upstream failed and no fallback configured",
                details={"reason": reason},
            )
        _log.warning("tracking.fallback_engaged", reference=reference, reason=reason)
        shipment = await self._fallback.fetch(reference)
        await self._cache_set(reference, shipment)
        return shipment
