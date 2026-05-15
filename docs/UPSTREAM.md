# Upstream — DSV / DB Schenker tracking

> Investigation notes for the `tracking` domain's client.
>
> Captured 2026-05-16 from Chrome devtools + JS bundle archaeology of
> `mydsv.dsv.com/app/tracking-public/`.

## Host migration

`www.dbschenker.com/app/tracking-public` now **302-redirects** to
`mydsv.dsv.com/app/tracking-public` following the DSV / Schenker integration.
Our client targets `mydsv.dsv.com` directly to skip the redirect hop.

## Base URLs

| Constant in bundle | Value |
|---|---|
| `backendUrl` (public) | `/nges-portal/api/public/tracking-public` |
| `publicTrackingBackendUrl` | `/nges-portal/api/public/tracking/v1` |
| `publicTrackingBaseUrl` (SPA root) | `https://mydsv.dsv.com/app/tracking-public` |
| `backendApiVersion` | `4` (sent as `X-Version: 4`) |

## Resolver flow

When the SPA boots with `?refNumber=<ref>` it issues:

```
GET /nges-portal/api/public/tracking-public/shipments?query=<ref>
```

The response (when not rate-limited) returns a list of matching shipments
keyed by transport type. The SPA then rewrites the URL to
`uiMode=details-{type}` (observed: `details-se` for Swedish road shipments)
and fetches the corresponding type-specific endpoint.

## Type-specific detail endpoints

Derived from the bundle constants:

| Type | Path (suffix from `backendUrl`) |
|---|---|
| Land (generic) | `/shipment/land/` |
| Land — Sweden | `/shipments/land/se` |
| Ocean | `/shipment/ocean/` |
| Air | `/shipment/air/` |
| Air/Ocean overview | `/shipment/air-ocean/search` |
| AU / NZ (domestic) | `/shipment/au/` |
| DSV (consolidated) | `/shipments/dsv` |
| ATOL | `/shipments/atol` |
| COS | `/shipments/cos` |

The `track_shipment` tool's job: call the resolver, then dispatch to the
correct detail endpoint based on the resolver's type hint.

## Headers required

The SPA sends, and the server expects, on every API call:

- `Accept: application/json, text/plain, */*`
- `X-Version: 4`
- `X-XSRF-TOKEN: <value of XSRF-TOKEN cookie>`
- A realistic `User-Agent`
- `Referer: https://mydsv.dsv.com/app/tracking-public/...`

XSRF cookies are minted by a `GET` to the SPA root.

## Status codes

- `200` — JSON body (resolver) or shipment detail.
- `404` — reference not found.
- `429` — rate limited by IP. Backoff or rotate egress IPs. Aggressive on
  rapid identical probes.
- `5xx` — transient upstream.

## Implications for the client

1. **Two-step fetch.** Resolver → detail. Cache the resolver result for the
   request lifetime to avoid double-spending quota.
2. **Cookie + XSRF priming.** Hit the SPA root once at process boot (or per
   call if cookies expire), parse `XSRF-TOKEN`, attach as header.
3. **Type-aware parsing.** Each detail endpoint has its own payload shape.
   Isolate parsers per type behind a uniform `Shipment` schema.
4. **Fallback path.** When the JSON endpoint 429s or returns an unexpected
   shape, fall back to a headless-browser scrape of the SPA. Slower but
   sees what a human sees.

## Risk register

| Risk | Mitigation |
|---|---|
| Schema drift on any detail endpoint | Schema-drift detector (sprint 4) compares parsed payload against a checksum of expected keys; logs warning + parse_error on mismatch. |
| Bundle URL constants change | Capture constants at runtime by fetching `runtime.*.js` + `main.*.js`; cache constants in `shared/config`. (Sprint 4 stretch.) |
| Aggressive rate limits per IP | Circuit breaker (sprint 4); response cache (60s TTL); pluggable egress for rotating IPs. |
| ToS / robots posture | Public, unauthenticated tracking is the SPA's documented use. Our request rate must stay below the SPA's normal load. |

## Decision Log

**2026-05-16: Target `mydsv.dsv.com` directly, not `www.dbschenker.com`.**
Saves the 302 hop and reflects post-acquisition reality. Old hostname kept
as a fallback in config in case DNS flips.

**2026-05-16: Two-step fetch baked into the client, not the tool.**
Tool sees one round-trip; the client hides resolver+detail. Keeps the MCP
contract simple and lets us add caching/short-circuits without changing the
domain surface.

**2026-05-16: Headless-browser fallback explicitly in scope.**
Sprint 1 ships the JSON path; sprint 4 adds Playwright fallback. Many CI
environments + the public IP space see rate limits we cannot avoid; the
fallback is the safety net.
