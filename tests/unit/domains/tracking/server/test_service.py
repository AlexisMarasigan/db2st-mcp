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
