"""Unit tests for the tracking-domain tool handlers.

Uses a fake `TrackingService` to keep tests purely on the tool contract:
input validation + delegating to the service + returning the right shape.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from db2st_mcp.domains.tracking.server.tool import (
    TrackShipmentArgs,
    TrackShipmentEventsArgs,
    track_shipment,
    track_shipment_events,
)
from db2st_mcp.domains.tracking.shared.schemas import Shipment, TrackingEvent


class _FakeService:
    """Stand-in matching the subset of TrackingService the tools use."""

    def __init__(self, shipment: Shipment | None = None) -> None:
        self.called_with: str | None = None
        self._shipment = shipment or Shipment(reference="X", type="land_se")

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


# --- track_shipment_events ---------------------------------------------------


@pytest.mark.asyncio
async def test_events_returns_only_history() -> None:
    """The events tool returns just the timeline — no sender/receiver
    envelope. Verifies the slimmer shape that justifies the second tool.
    """
    events = [
        TrackingEvent(at=datetime(2026, 5, 12, 8, 15, tzinfo=UTC), status="PICKED_UP"),
        TrackingEvent(at=datetime(2026, 5, 15, 9, 5, tzinfo=UTC), status="DELIVERED"),
    ]
    service = _FakeService(
        Shipment(reference="1806203236", type="land_se", history=events)
    )
    args = TrackShipmentEventsArgs(reference="1806203236")
    result = await track_shipment_events(args, service=service)  # type: ignore[arg-type]
    assert result == events
    assert service.called_with == "1806203236"


@pytest.mark.asyncio
async def test_events_returns_empty_list_when_no_history() -> None:
    service = _FakeService(Shipment(reference="X", type="land"))
    args = TrackShipmentEventsArgs(reference="X-REF")
    result = await track_shipment_events(args, service=service)  # type: ignore[arg-type]
    assert result == []


def test_events_reference_min_length_enforced() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrackShipmentEventsArgs(reference="abc")


# --- whitespace-only references --------------------------------------------


@pytest.mark.asyncio
async def test_track_shipment_rejects_whitespace_only_reference() -> None:
    """Pydantic min_length=4 accepts `"    "` (4 spaces) because it's 4
    chars. The `args.reference.strip()` check in the handler defends
    against this: real references aren't whitespace.
    """
    from db2st_mcp.shared.errors import InvalidInputError

    service = _FakeService()
    args = TrackShipmentArgs(reference="    ")
    with pytest.raises(InvalidInputError):
        await track_shipment(args, service=service)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_track_shipment_events_rejects_whitespace_only_reference() -> None:
    from db2st_mcp.shared.errors import InvalidInputError

    service = _FakeService()
    args = TrackShipmentEventsArgs(reference="    ")
    with pytest.raises(InvalidInputError):
        await track_shipment_events(args, service=service)  # type: ignore[arg-type]
