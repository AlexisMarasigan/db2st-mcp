"""Build the MCP server (FastMCP, Streamable HTTP, stateless).

The MCP server is mounted into the parent FastAPI app at `/mcp`. Tools are
registered here, but their implementation is owned by the relevant domain.

Tools added in sprint 1: `track_shipment`.
"""

from __future__ import annotations

from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP

from db2st_mcp.domains.tracking.server.service import TrackingService
from db2st_mcp.domains.tracking.server.tool import (
    TrackShipmentArgs,
    track_shipment,
)
from db2st_mcp.domains.tracking.shared.schemas import Shipment

_log = structlog.get_logger(__name__)


def build_mcp_server(tracking_service: TrackingService) -> FastMCP:
    """Build the MCP server with all domain tools registered."""
    mcp = FastMCP(
        "db2st-mcp",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
    )

    @mcp.tool(
        name="track_shipment",
        description=(
            "Look up a DB Schenker / DSV shipment by tracking reference number. "
            "Returns sender, receiver, package details, and the full tracking history."
        ),
    )
    async def _track_shipment(reference: str) -> dict[str, Any]:
        args = TrackShipmentArgs(reference=reference)
        shipment: Shipment = await track_shipment(args, service=tracking_service)
        return shipment.model_dump(mode="json")

    _log.info("mcp.tools_registered", tools=["track_shipment"])
    return mcp
