"""MCP tool handler for `track_shipment`.

Sprint 0 stub. Sprint 1 wires the SchenkerClient + parser.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from db2st_mcp.domains.tracking.shared import Shipment
from db2st_mcp.shared.errors import InvalidInputError


class TrackShipmentArgs(BaseModel):
    """Input schema for the `track_shipment` MCP tool."""

    reference: str = Field(min_length=4, max_length=64, description="DB Schenker tracking reference.")


async def track_shipment_tool(args: TrackShipmentArgs) -> Shipment:
    """Resolve a tracking reference to a structured `Shipment`.

    Sprint 0 stub raises until the SchenkerClient lands in sprint 1.
    """
    if not args.reference.strip():
        raise InvalidInputError("reference must not be empty")
    raise NotImplementedError("track_shipment is wired in sprint 1")
