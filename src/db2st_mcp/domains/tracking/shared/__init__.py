"""tracking domain — shared contracts (schemas, errors).

Importable from client/server code. Has no dependency on tracking internals.
"""

from db2st_mcp.domains.tracking.shared.schemas import (
    Address,
    PackageInfo,
    Party,
    Shipment,
    TrackingEvent,
)

__all__ = [
    "Address",
    "PackageInfo",
    "Party",
    "Shipment",
    "TrackingEvent",
]
