"""End-to-end inside the tracking domain: service → client → parser."""

from __future__ import annotations

import httpx
import pytest
import respx

from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient
from db2st_mcp.domains.tracking.server.service import TrackingService
from db2st_mcp.domains.tracking.shared.schemas import Shipment
from db2st_mcp.shared.cache import TTLCache
from db2st_mcp.shared.circuit_breaker import CircuitBreaker
from db2st_mcp.shared.errors import UpstreamUnavailableError

API = "https://mydsv.dsv.com"


def _make_client() -> SchenkerClient:
    return SchenkerClient(client=httpx.AsyncClient(base_url=API, headers={"x-version": "4"}))


@pytest.mark.asyncio
async def test_service_happy_path_returns_parsed_shipment() -> None:
    client = _make_client()
    service = TrackingService(client)

    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(
            200, json=[{"id": "1806203236", "type": "land_se"}]
        )
        mock.get("/nges-portal/api/public/tracking-public/shipments/land/se/1806203236").respond(
            200,
            json={
                "sender": {"name": "Acme"},
                "receiver": {"name": "Globex"},
                "events": [{"timestamp": "2026-05-15T10:00:00Z", "status": "DELIVERED"}],
            },
        )

        shipment = await service.get_shipment("1806203236")

    assert shipment.reference == "1806203236"
    assert shipment.type == "land_se"
    assert shipment.sender.name == "Acme"
    assert shipment.receiver.name == "Globex"
    assert len(shipment.history) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_service_cache_returns_hit_without_calling_upstream() -> None:
    client = _make_client()
    cache: TTLCache[Shipment] = TTLCache(maxsize=4, ttl_seconds=60)
    service = TrackingService(client, cache=cache)

    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(
            200, json=[{"id": "X", "type": "land"}]
        )
        mock.get("/nges-portal/api/public/tracking-public/shipment/land/X").respond(
            200, json={"sender": {"name": "S"}, "receiver": {"name": "R"}}
        )

        first = await service.get_shipment("X")
        second = await service.get_shipment("X")

    assert first.sender.name == "S"
    assert second is first  # cache returns the exact same instance
    await client.aclose()


@pytest.mark.asyncio
async def test_service_breaker_opens_after_failures() -> None:
    client = _make_client()
    breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=10)
    service = TrackingService(client, breaker=breaker)

    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(429)
        for _ in range(2):
            with pytest.raises(UpstreamUnavailableError):
                await service.get_shipment("Y")

    # Now the breaker should be open; without a fallback the service raises.
    with pytest.raises(UpstreamUnavailableError):
        await service.get_shipment("Y")
    assert breaker.open is True
    await client.aclose()


@pytest.mark.asyncio
async def test_service_404_records_breaker_success() -> None:
    """A `NotFoundError` from upstream is a healthy "no such record"
    response, not a service failure. The breaker should treat it as
    success (resetting any prior failures) and re-raise.
    """
    from db2st_mcp.shared.errors import NotFoundError

    client = _make_client()
    breaker = CircuitBreaker(failure_threshold=5, cooldown_seconds=10)
    breaker.record_failure()  # prime so success-reset is observable
    service = TrackingService(client, breaker=breaker)

    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(404)
        with pytest.raises(NotFoundError):
            await service.get_shipment("missing")

    # Prior failures cleared by the success record.
    assert breaker.state == "closed"
    await client.aclose()


@pytest.mark.asyncio
async def test_service_falls_back_when_breaker_open_and_fallback_configured() -> None:
    """When the breaker is open and an HTML fallback is configured,
    the service routes to the fallback and caches the result.
    """

    class _StubFallback:
        def __init__(self, shipment: Shipment) -> None:
            self._shipment = shipment
            self.calls: list[str] = []

        async def fetch(self, reference: str) -> Shipment:
            self.calls.append(reference)
            return self._shipment

    client = _make_client()
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
    breaker.record_failure()  # force open
    assert breaker.open is True

    fallback_shipment = Shipment(
        reference="Z-REF", type="unknown", source="html_fallback"
    )
    fallback = _StubFallback(fallback_shipment)
    cache: TTLCache[Shipment] = TTLCache(maxsize=4, ttl_seconds=60)
    service = TrackingService(client, cache=cache, breaker=breaker, html_fallback=fallback)

    # Breaker is open → service skips the primary path and goes
    # straight to the fallback.
    shipment = await service.get_shipment("Z-REF")
    assert shipment is fallback_shipment
    assert fallback.calls == ["Z-REF"]
    # Result is cached so a repeat doesn't hit the fallback again.
    again = await service.get_shipment("Z-REF")
    assert again is fallback_shipment
    assert fallback.calls == ["Z-REF"]  # still one call

    await client.aclose()
