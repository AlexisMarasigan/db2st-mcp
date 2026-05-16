"""Build the MCP server (FastMCP, Streamable HTTP, stateless).

The MCP server is mounted into the parent FastAPI app at `/mcp`. Tools are
registered here, but their implementation is owned by the relevant domain.

Tools:
- `track_shipment` (sprint 1) — full Shipment record.
- `track_shipment_events` (sprint 4 stretch) — events timeline only.
"""

from __future__ import annotations

from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from db2st_mcp.domains.tracking.server.service import TrackingService
from db2st_mcp.domains.tracking.server.tool import (
    TrackShipmentArgs,
    TrackShipmentEventsArgs,
    track_shipment,
    track_shipment_events,
)
from db2st_mcp.domains.tracking.shared.schemas import Shipment
from db2st_mcp.shared.config import get_settings

_log = structlog.get_logger(__name__)


def _transport_security() -> TransportSecuritySettings | None:
    """Build a custom `TransportSecuritySettings` if env-supplied hosts exist.

    Returning `None` lets FastMCP apply its default (localhost + 127.0.0.1 +
    [::1] with any port). Returning a populated settings object widens the
    allowed-hosts list to include the operator's production hostnames.
    """
    extra = [h.strip() for h in get_settings().mcp_allowed_hosts.split(",") if h.strip()]
    if not extra:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", *extra],
    )


def build_mcp_server(tracking_service: TrackingService) -> FastMCP:
    """Build the MCP server with all domain tools registered."""
    mcp = FastMCP(
        "db2st-mcp",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=_transport_security(),
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

    @mcp.tool(
        name="track_shipment_events",
        description=(
            "Return the events timeline (chronological status updates) for a "
            "DB Schenker / DSV tracking reference. Lighter than `track_shipment` "
            "for clients that only care about polling status changes."
        ),
    )
    async def _track_shipment_events(reference: str) -> list[dict[str, Any]]:
        args = TrackShipmentEventsArgs(reference=reference)
        events = await track_shipment_events(args, service=tracking_service)
        return [e.model_dump(mode="json") for e in events]

    _log.info(
        "mcp.tools_registered",
        tools=["track_shipment", "track_shipment_events"],
    )
    return mcp
