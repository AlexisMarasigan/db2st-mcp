"""Unit tests for `SchenkerClient` using respx to mock httpx.

Network is never hit. Covers happy path, 404→NotFoundError, 429+5xx→
UpstreamUnavailableError, and the XSRF priming flow.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient
from db2st_mcp.shared.errors import NotFoundError, UpstreamUnavailableError

API = "https://mydsv.dsv.com"


@pytest.fixture
def client() -> SchenkerClient:
    return SchenkerClient(
        client=httpx.AsyncClient(
            base_url=API,
            headers={"x-version": "4"},
            follow_redirects=True,
        )
    )


@pytest.mark.asyncio
async def test_resolve_returns_first_candidate(client: SchenkerClient) -> None:
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(
            200,
            html="<html/>",
            headers={"set-cookie": "XSRF-TOKEN=abc; Path=/"},
        )
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(
            200,
            json=[{"id": "1806203236", "type": "land_se"}],
        )
        result = await client.resolve("1806203236")
    assert result == ("land_se", "1806203236")
    await client.aclose()


@pytest.mark.asyncio
async def test_resolve_404_raises_not_found(client: SchenkerClient) -> None:
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(404)
        with pytest.raises(NotFoundError):
            await client.resolve("000")
    await client.aclose()


@pytest.mark.asyncio
async def test_resolve_429_raises_upstream_unavailable(client: SchenkerClient) -> None:
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(429)
        with pytest.raises(UpstreamUnavailableError):
            await client.resolve("X")
    await client.aclose()


@pytest.mark.asyncio
async def test_resolve_5xx_raises_upstream_unavailable(client: SchenkerClient) -> None:
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(502)
        with pytest.raises(UpstreamUnavailableError):
            await client.resolve("X")
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_detail_dispatches_to_land_se_endpoint(
    client: SchenkerClient,
) -> None:
    payload = {"sender": {"name": "S"}, "receiver": {"name": "R"}}
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        route = mock.get(
            "/nges-portal/api/public/tracking-public/shipments/land/se/1806203236"
        ).respond(200, json=payload)
        result = await client.fetch_detail("land_se", "1806203236")
    assert route.called
    assert result == payload
    await client.aclose()


@pytest.mark.asyncio
async def test_xsrf_token_is_forwarded_as_header(client: SchenkerClient) -> None:
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(
            200,
            html="<html/>",
            headers={"set-cookie": "XSRF-TOKEN=secret-xsrf; Path=/"},
        )
        api_route = mock.get("/nges-portal/api/public/tracking-public/shipments").respond(
            200, json=[{"id": "X", "type": "land"}]
        )

        await client.resolve("X")

    sent = api_route.calls.last.request
    assert sent.headers.get("x-xsrf-token") == "secret-xsrf"
    await client.aclose()
