"""tracking domain — shared contracts (schemas, errors).

Consumers import directly from the submodule, e.g.:

    from db2st_mcp.domains.tracking.shared.schemas import Shipment

No package-level re-exports — keeps the contract surface in one place
(`schemas.py`) and avoids drift when new symbols are added.
"""
