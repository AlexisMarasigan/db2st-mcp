"""MCP tool handlers for the tracking domain.

Thin wrappers around `TrackingService`. The tools exist to:
- normalize input,
- run the orchestration,
- shape MCP-friendly errors.

Two tools today:
- `track_shipment` — the full structured `Shipment` (sender, receiver,
  package, history).
- `track_shipment_events` — events timeline only, for clients that
  poll for status updates without needing the heavier shipment
  envelope. (Sprint-4 stretch from the original brief.)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from db2st_mcp.domains.tracking.server.service import TrackingService
from db2st_mcp.domains.tracking.shared.schemas import Shipment, TrackingEvent
from db2st_mcp.shared.errors import InvalidInputError


class TrackShipmentArgs(BaseModel):
    """Input schema for the `track_shipment` MCP tool."""

    reference: str = Field(
        min_length=4,
        max_length=64,
        description="DB Schenker / DSV tracking reference number.",
    )


class TrackShipmentEventsArgs(BaseModel):
    """Input schema for the `track_shipment_events` MCP tool."""

    reference: str = Field(
        min_length=4,
        max_length=64,
        description="DB Schenker / DSV tracking reference number.",
    )


async def track_shipment(
    args: TrackShipmentArgs,
    *,
    service: TrackingService,
) -> Shipment:
    """Resolve a tracking reference to a structured `Shipment`."""
    if not args.reference.strip():
        raise InvalidInputError("reference must not be empty")
    return await service.get_shipment(args.reference)


async def track_shipment_events(
    args: TrackShipmentEventsArgs,
    *,
    service: TrackingService,
) -> list[TrackingEvent]:
    """Return only the events timeline for a tracking reference.

    Useful for poll-style clients that just want the chronological
    status updates. Per-package event splits (one timeline per colli)
    are a future refinement — see `docs/ROADMAP.md` Stretch section.
    """
    if not args.reference.strip():
        raise InvalidInputError("reference must not be empty")
    shipment = await service.get_shipment(args.reference)
    return shipment.history
