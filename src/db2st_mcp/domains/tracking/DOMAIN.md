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
    name: str = ""
    address: Address = Field(default_factory=Address)

class PackageInfo(BaseModel):
    weight_kg: Decimal | None = None
    length_cm: int | None = None
    width_cm: int | None = None
    height_cm: int | None = None
    piece_count: int = 1
    volume_m3: Decimal | None = None

class TrackingEvent(BaseModel):
    at: datetime
    location: str | None = None
    status: str
    description: str | None = None

class Shipment(BaseModel):
    reference: str
    type: ShipmentType = "unknown"
    sender: Party = Field(default_factory=Party)
    receiver: Party = Field(default_factory=Party)
    package: PackageInfo = Field(default_factory=PackageInfo)
    history: list[TrackingEvent] = Field(default_factory=list)
    source: Literal["json", "html_fallback"] = "json"
```

All models use `ConfigDict(extra="forbid")` so unexpected upstream
fields surface as a `ParseError` rather than silently passing through.
The MCP framework serialises the returned `Shipment` via
`model_dump(mode="json")`, so callers see ISO-8601 strings and
JSON-safe Decimals.

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
| Reference not found (upstream 404 or empty resolver) | `NotFoundError` | `not_found` |
| Upstream timeout, 5xx, 429, other 4xx, network/connection error, non-JSON response body | `UpstreamUnavailableError` | `upstream_unavailable` |
| Upstream payload shape change (detail endpoint returns non-dict, or parse raises) | `ParseError` | `parse_error` |
| Reference format invalid (empty / whitespace-only / outside `[4..64]` chars) | `InvalidInputError` | `invalid_input` |

## Observability

Structured log events emitted by the orchestrator and its primitives:

| Event | Level | When |
|---|---|---|
| `tracking.cache_hit` | info | `TrackingService` served the response from cache (memory or Upstash). |
| `tracking.cache_get_failed` | warning | The cache backend (typically `UpstashCache` when Upstash is unreachable) raised on read. The service degrades to a miss and falls through to the upstream path — the request still succeeds. Includes `reference` and `cause` (the exception class name). |
| `tracking.cache_set_failed` | warning | Same idea for writes: an Upstash outage on `set()` after a successful upstream fetch would otherwise lose the result. Swallowed so the request returns the shipment. Includes `reference` and `cause`. |
| `tracking.fallback_engaged` | warning | Primary upstream failed (breaker open or error); HTML fallback was invoked. Includes `reason`. |
| `html_fallback.empty` | warning | The Playwright fallback scraped but returned no content. The tool maps this to `NotFoundError`; the log line surfaces it for ops. Includes `reference`. |
| `html_fallback.playwright_error` | warning | Playwright itself errored (e.g., `Page.goto: Timeout 30000ms exceeded`, navigation crash). The tool maps it to `UpstreamUnavailableError` so the wire response stays in the project taxonomy and the breaker counts it as an upstream failure. Includes `reference` and `exc` (the Playwright exception class name). |
| `circuit_breaker.opened` | warning | Failure threshold hit. Includes `failures`, `threshold`, `cooldown_seconds`. The upstream is now short-circuited until cooldown. |
| `circuit_breaker.closed` | info | Open → closed recovery: a successful request after the breaker had tripped. |
| `schema.first_seen` | info | A new `(endpoint, fingerprint)` pair recorded for the first time. Normal at boot. |
| `schema.drift` | warning | A *previously-seen* endpoint returned a payload with a *new* top-level key-shape fingerprint. Strong signal that the upstream changed shape; the parser may start raising `ParseError`. Includes `endpoint` (`resolver` or `detail:<ShipmentType>`) and `fingerprint`. |

Auth domain emits the parallel `auth.failure` / `auth.quota_exhausted`
events — see [docs/AUTH.md](../../../../docs/AUTH.md) Observability.

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

**2026-05-16: Pydantic models for the domain boundary; function signatures for the wire schema.**
The domain contract (`Shipment`, `Party`, `PackageInfo`, ...) lives in
`shared/schemas.py`. FastMCP, however, derives the MCP tool's
*inputSchema* from the registered function's parameter annotations
(`reference: str`), not from the `TrackShipmentArgs` Pydantic
model — so the wire JSON Schema sees `{reference: string}` without
the `min_length=4 / max_length=64` constraints. The args Pydantic
models are used inside the handler for internal validation (iter-171
re-raises any `ValidationError` as a clean `InvalidInputError` so the
client never sees Pydantic internals). The output side is closer to
the original ideal: handlers return `Shipment.model_dump(mode="json")`
so the response shape genuinely is the contract.

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

**2026-05-16: `track_shipment_events` ships shipment-level, not per-colli.**
The original brief's bonus asked for "individual tracking events per
package". The current upstream payload exposes a single shipment-level
event timeline (`Shipment.history`); per-package event arrays are not
observable from this rate-limited dev IP. Decision: ship the lighter
events tool now with the existing shape (real value for poll-style
clients today) and defer the per-package split (`Shipment.packages:
list[Package]` with per-package `events`) to a future iteration that
can observe the real per-package JSON. Speculating a schema without
ground truth would have been a guess that future-us would have to
unwind.
