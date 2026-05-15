"""Unit tests for the `track_shipment` tool handler.

Uses a fake `TrackingService` to keep the test purely on the tool contract:
input validation + delegating to the service + returning the `Shipment`.
"""

from __future__ import annotations

import pytest

from db2st_mcp.domains.tracking.server.tool import (
    TrackShipmentArgs,
    track_shipment,
)
from db2st_mcp.domains.tracking.shared.schemas import Shipment


class _FakeService:
    """Stand-in matching the subset of TrackingService that the tool uses."""

    def __init__(self) -> None:
        self.called_with: str | None = None
        self._shipment = Shipment(reference="X", type="land_se")

    async def get_shipment(self, reference: str) -> Shipment:
        self.called_with = reference
        return self._shipment


@pytest.mark.asyncio
async def test_happy_path_returns_shipment() -> None:
    service = _FakeService()
    args = TrackShipmentArgs(reference="1806203236")
    shipment = await track_shipment(args, service=service)  # type: ignore[arg-type]
    assert shipment.reference == "X"
    assert service.called_with == "1806203236"


def test_reference_min_length_enforced_by_pydantic() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrackShipmentArgs(reference="abc")
