"""Real-upstream integration tests.

These tests hit `mydsv.dsv.com` directly with the 11 sample references
from the original brief. They're marked `integration` and **excluded
from the default pytest run** because:

- DSV rate-limits aggressive callers (the development machine's IP is
  currently 429-banned).
- A green run requires network access and a clean egress IP.

Run them explicitly when you want real-upstream confidence:

    uv run pytest -m integration

The tests are intentionally lenient: they assert *structural* correctness
(the parser produced a `Shipment`, the upstream resolved a type) rather
than specific shipment data, because real shipment records age out of
DSV's tracking window over time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from db2st_mcp.domains.tracking.server.schenker_client import SchenkerClient
from db2st_mcp.domains.tracking.server.service import TrackingService
from db2st_mcp.domains.tracking.shared.schemas import Shipment
from db2st_mcp.shared.errors import NotFoundError, UpstreamUnavailableError

pytestmark = [pytest.mark.integration]


# The 11 sample references from the Sendify / DSV brief.
SAMPLE_REFS = [
    "1806203236",
    "1806290829",
    "1806273700",
    "1806272330",
    "1806271886",
    "1806270433",
    "1806268072",
    "1806267579",
    "1806264568",
    "1806258974",
    "1806256390",
]


@pytest.fixture
async def service() -> AsyncIterator[TrackingService]:
    client = SchenkerClient()
    try:
        yield TrackingService(client)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", SAMPLE_REFS)
async def test_sample_reference_returns_well_formed_shipment(
    reference: str, service: TrackingService
) -> None:
    """A sample ref either resolves to a `Shipment` or surfaces a clean
    domain error. Anything else (raw httpx exception, KeyError, etc) is
    a regression.
    """
    try:
        shipment = await service.get_shipment(reference)
    except NotFoundError:
        # Ref aged out of upstream's tracking window — acceptable.
        return
    except UpstreamUnavailableError:
        pytest.skip(
            f"upstream unavailable / rate-limited for {reference}; "
            "re-run from an unblocked egress IP"
        )

    assert isinstance(shipment, Shipment)
    assert shipment.reference == reference
    assert shipment.type in {
        "land",
        "land_se",
        "land_au",
        "ocean",
        "air",
        "dsv",
        "atol",
        "cos",
        "unknown",
    }
    assert shipment.source == "json"
