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
@pytest.mark.parametrize(
    ("type_hint", "suffix"),
    [
        ("land", "/shipment/land/"),
        ("land_au", "/shipment/au/"),
        ("ocean", "/shipment/ocean/"),
        ("air", "/shipment/air/"),
        ("dsv", "/shipments/dsv/"),
        ("atol", "/shipments/atol/"),
        ("cos", "/shipments/cos/"),
        ("unknown", "/shipment/land/"),  # safe default
    ],
)
async def test_fetch_detail_dispatch_table(
    client: SchenkerClient, type_hint: str, suffix: str
) -> None:
    payload = {"sender": {"name": "S"}, "receiver": {"name": "R"}}
    upstream_id = "X-REF"
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        route = mock.get(f"/nges-portal/api/public/tracking-public{suffix}{upstream_id}").respond(
            200, json=payload
        )
        await client.fetch_detail(type_hint, upstream_id)  # type: ignore[arg-type]
    assert route.called
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_detail_raises_parse_error_for_non_dict_payload(
    client: SchenkerClient,
) -> None:
    """Upstream returning a JSON array or scalar where a shipment object
    is expected should surface as a domain-level ParseError, not propagate
    a TypeError out of the parser.
    """
    from db2st_mcp.shared.errors import ParseError

    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments/land/se/X-REF").respond(
            200, json=["not", "a", "dict"]
        )
        with pytest.raises(ParseError):
            await client.fetch_detail("land_se", "X-REF")
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


# --- error paths -----------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_empty_list_raises_not_found(client: SchenkerClient) -> None:
    """200 OK with an empty shipments list should surface as NotFoundError
    (line 109 of schenker_client.py). The resolver returning [] means
    DSV has no record of the reference.
    """
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(200, json=[])
        with pytest.raises(NotFoundError):
            await client.resolve("0000000000")
    await client.aclose()


@pytest.mark.asyncio
async def test_xsrf_prime_failure_surfaces_as_upstream_unavailable(
    client: SchenkerClient,
) -> None:
    """If the initial SPA GET (XSRF cookie prime) raises a connection
    error, `_prime_xsrf` translates it into `UpstreamUnavailableError`.
    """
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").mock(side_effect=httpx.ConnectError("connection refused"))
        with pytest.raises(UpstreamUnavailableError):
            await client.resolve("X")
    await client.aclose()


@pytest.mark.asyncio
async def test_upstream_timeout_becomes_upstream_unavailable(
    client: SchenkerClient,
) -> None:
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").mock(
            side_effect=httpx.TimeoutException("read timeout")
        )
        with pytest.raises(UpstreamUnavailableError, match="timeout"):
            await client.resolve("X")
    await client.aclose()


@pytest.mark.asyncio
async def test_upstream_connection_error_becomes_upstream_unavailable(
    client: SchenkerClient,
) -> None:
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").mock(
            side_effect=httpx.ConnectError("network down")
        )
        with pytest.raises(UpstreamUnavailableError, match="connection"):
            await client.resolve("X")
    await client.aclose()


@pytest.mark.asyncio
async def test_4xx_other_than_404_429_becomes_upstream_unavailable(
    client: SchenkerClient,
) -> None:
    """A 400/401/403 is not in our explicit-error set; the catch-all
    `>= 400` branch (line 175) translates them to upstream_unavailable
    so callers see a consistent error taxonomy.
    """
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(403)
        with pytest.raises(UpstreamUnavailableError, match="403"):
            await client.resolve("X")
    await client.aclose()


@pytest.mark.asyncio
async def test_non_json_response_becomes_upstream_unavailable(
    client: SchenkerClient,
) -> None:
    """Upstream returning a 200 with text/html (e.g., maintenance page)
    cannot be JSON-decoded — surfaces as upstream_unavailable.
    """
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(
            200,
            text="<html><body>Down for maintenance</body></html>",
            headers={"content-type": "text/html"},
        )
        with pytest.raises(UpstreamUnavailableError, match="non-JSON"):
            await client.resolve("X")
    await client.aclose()


@pytest.mark.asyncio
async def test_context_manager_closes_client() -> None:
    """`async with SchenkerClient() as c` returns the client and closes
    it on exit (lines 87 + 90).
    """
    async with SchenkerClient() as c:
        assert isinstance(c, SchenkerClient)
    # After exit, the inner httpx client should be closed.
    assert c._client.is_closed


@pytest.mark.asyncio
async def test_drift_detector_is_called_on_resolver_and_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The schema-drift detector ships in `shared/drift.py` and was
    listed in Sprint 4. Until iter 126 it had no production caller —
    only its own unit tests. This pins the wiring: both upstream
    fetch sites (resolver, detail) must invoke `drift_check` with
    a stable endpoint identifier so a real upstream-payload shape
    change shows up as `schema.drift` / `schema.first_seen` in logs.
    """
    from db2st_mcp.domains.tracking.server import schenker_client as sc_module

    calls: list[tuple[str, object]] = []

    def _spy(endpoint: str, payload: object) -> None:
        calls.append((endpoint, payload))

    monkeypatch.setattr(sc_module, "drift_check", _spy)

    client = SchenkerClient(
        client=httpx.AsyncClient(
            base_url=API,
            headers={"x-version": "4"},
            follow_redirects=True,
        )
    )
    with respx.mock(base_url=API) as mock:
        mock.get("/app/tracking-public/").respond(200, html="<html/>")
        mock.get("/nges-portal/api/public/tracking-public/shipments").respond(
            200, json=[{"id": "1806203236", "type": "land_se"}]
        )
        mock.get("/nges-portal/api/public/tracking-public/shipments/land/se/1806203236").respond(
            200, json={"id": "1806203236"}
        )
        await client.resolve("1806203236")
        await client.fetch_detail("land_se", "1806203236")

    endpoints = [endpoint for endpoint, _ in calls]
    assert "resolver" in endpoints
    assert "detail:land_se" in endpoints
    await client.aclose()
