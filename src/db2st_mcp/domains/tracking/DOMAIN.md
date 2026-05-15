# DOMAIN: tracking

> Shipment tracking via DB Schenker's public tracking endpoint.

## Capability

Given a Schenker tracking reference, return structured shipment data:

- Sender (name, address)
- Receiver (name, address)
- Package details (weight, dimensions, piece count, ...)
- Tracking history (chronological events)
- *(stretch)* per-package events

## Public surface

| Symbol | Where | What |
|---|---|---|
| `Shipment`, `Party`, `PackageInfo`, `TrackingEvent` | `shared/schemas.py` | Pydantic models (contract). |
| `TrackingError` | `shared/errors.py` | Domain-scoped error subclasses. |
| `SchenkerClient.fetch(ref)` | `server/schenker_client.py` | Raw fetch → normalized. |
| `track_shipment_tool(args)` | `server/tool.py` | MCP tool handler. Registered by `apps/server`. |

## Contracts

```python
class Party(BaseModel):
    name: str
    address: Address

class PackageInfo(BaseModel):
    weight_kg: Decimal | None
    dimensions_cm: tuple[int, int, int] | None
    piece_count: int

class TrackingEvent(BaseModel):
    at: datetime
    location: str | None
    status: str
    description: str | None

class Shipment(BaseModel):
    reference: str
    sender: Party
    receiver: Party
    package: PackageInfo
    history: list[TrackingEvent]
```

The MCP tool returns `Shipment.model_dump(mode="json")`.

## Internal pieces

| File | Role |
|---|---|
| `server/schenker_client.py` | HTTP client; tries JSON API first, HTML scrape only as fallback. |
| `server/parser.py` | Raw upstream → `Shipment`. Isolated for schema-drift tests. |
| `server/tool.py` | Thin MCP tool handler; calls client + maps errors. |

## Upstream

`https://www.dbschenker.com/app/tracking-public/` — the public SPA. Sprint 1
investigation: confirm or refute the existence of a stable JSON endpoint by
inspecting network calls; favour that over scraping.

## Dependencies on other domains

None.

## Error mapping

| Cause | Domain error | Code |
|---|---|---|
| Reference not found | `NotFoundError` | `not_found` |
| Upstream timeout / 5xx | `UpstreamUnavailableError` | `upstream_unavailable` |
| Upstream payload shape change | `ParseError` | `parse_error` |
| Reference format invalid | `InvalidInputError` | `invalid_input` |

## Tests

- `tests/unit/domains/tracking/server/` — parser, client (recorded fixtures).
- `tests/integration/test_tracking.py` — hits real Schenker for sample refs (marked `integration`).
- `tests/e2e/` — full server + MCP client, also runs against sample refs.

## Sample references (from the original brief)

`1806203236 1806290829 1806273700 1806272330 1806271886 1806270433 1806268072
1806267579 1806264568 1806258974 1806256390`

## Decision Log

**2026-05-16: Pydantic models are the contract.**
Domain boundary contract lives in `shared/schemas.py`. The MCP tool schema is derived from the same models — single source of truth.

**2026-05-16: Parser isolated from client.**
A parser-only test suite lets us add upstream fixtures over time without rerunning network code, and surfaces schema drift fast.
