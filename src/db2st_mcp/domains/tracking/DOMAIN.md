# DOMAIN: tracking

> Shipment tracking via DB Schenker's public tracking endpoint.

## Capability

Given a Schenker tracking reference, return structured shipment data:

- Sender (name, address)
- Receiver (name, address)
- Package details (weight, dimensions, piece count, ...)
- Tracking history (chronological events) — also exposed standalone
  via the `track_shipment_events` tool for poll-style clients.
- *(stretch)* per-package events (one timeline per colli) — pending
  upstream-payload observation; see `docs/ROADMAP.md`.

## Public surface

| Symbol | Where | What |
|---|---|---|
| `Shipment`, `Party`, `Address`, `PackageInfo`, `TrackingEvent`, `ShipmentType` | `shared/schemas.py` | Pydantic models (contract). |
| `SchenkerClient.resolve(ref)`, `.fetch_detail(type, id)` | `server/schenker_client.py` | Two-step upstream fetch (resolver → detail). |
| `TrackingService.get_shipment(ref)` | `server/service.py` | Orchestrator: cache → breaker → client → fallback. |
| `track_shipment(args, service=...)` | `server/tool.py` | Async MCP tool handler — returns the full `Shipment`. |
| `track_shipment_events(args, service=...)` | `server/tool.py` | Async MCP tool handler — returns only the events timeline. |
| `PlaywrightHtmlFallback` | `server/html_fallback.py` | Optional HTML scrape fallback (sprint 4). |

Domain errors come from `db2st_mcp.shared.errors` (`NotFoundError`,
`UpstreamUnavailableError`, `ParseError`, `InvalidInputError`).

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
| `server/schenker_client.py` | HTTP client. Hits the DSV public JSON API. |
| `server/parser.py` | Raw upstream → `Shipment`. Isolated for schema-drift tests. |
| `server/service.py` | Orchestrator. Owns cache + circuit breaker + fallback wiring. |
| `server/tool.py` | Thin MCP tool handler; calls `TrackingService` and maps errors. |
| `server/html_fallback.py` | Playwright SPA scrape — engaged when `DB2ST_HTML_FALLBACK=1`. |

## Upstream

`https://mydsv.dsv.com/app/tracking-public/` — the post-DSV-acquisition home
of the public SPA. The legacy `www.dbschenker.com/app/tracking-public`
host 302-redirects here. JSON API at
`/nges-portal/api/public/tracking-public`; see [docs/UPSTREAM.md](../../../../docs/UPSTREAM.md).

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

- `tests/unit/domains/tracking/server/` — parser, parser helpers, client,
  service orchestrator, HTML fallback, tool handler.
- `tests/integration/test_real_upstream.py` — parametrises every sample
  reference against the live DSV upstream (marked `integration`,
  deselected by default).
- `tests/e2e/test_mcp_stdio.py` — full server + MCP client over stdio.

## Sample references (from the original brief)

`1806203236 1806290829 1806273700 1806272330 1806271886 1806270433 1806268072
1806267579 1806264568 1806258974 1806256390`

## Decision Log

**2026-05-16: Pydantic models are the contract.**
Domain boundary contract lives in `shared/schemas.py`. The MCP tool schema is derived from the same models — single source of truth.

**2026-05-16: Parser isolated from client.**
A parser-only test suite lets us add upstream fixtures over time without rerunning network code, and surfaces schema drift fast.

**2026-05-16: Orchestration lives in `service.py`, not the tool handler.**
The MCP tool stays a one-liner; cache, circuit breaker, and HTML fallback
wiring all live in `TrackingService.get_shipment`. Future tools can reuse
the orchestrator without re-implementing the safety net.

**2026-05-16: HTML fallback recognises the "Shipment not found" SPA marker.**
The Playwright fallback raises `NotFoundError` instead of returning a
misleading "scraped" event so the JSON path and the fallback agree on the
error taxonomy.
