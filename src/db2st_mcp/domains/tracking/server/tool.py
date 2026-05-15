"""MCP tool handler for `track_shipment`.

Thin wrapper around `TrackingService`. The tool exists to:
- normalize input,
- run the orchestration,
- shape MCP-friendly errors.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from db2st_mcp.domains.tracking.server.service import TrackingService
from db2st_mcp.domains.tracking.shared.schemas import Shipment
from db2st_mcp.shared.errors import InvalidInputError


class TrackShipmentArgs(BaseModel):
    """Input schema for the `track_shipment` MCP tool."""

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
