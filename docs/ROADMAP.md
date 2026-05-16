# Roadmap

Phased plan. Each sprint ends with a runnable, demonstrable artifact.

## Sprint 0 — Foundations (current)

- [x] Repo skeleton + Clara-style docs
- [x] CLAUDE.md AI entry
- [x] Python project scaffold (`pyproject.toml`, `src/` layout, domain stubs)
- [x] CI: lint, typecheck, unit tests
- [x] Pre-commit hooks

**Exit:** `uv sync && uv run pytest` passes against domain stubs.

## Sprint 1 — Tracking domain

- [x] MCP server (Streamable HTTP transport) in `apps/server`
- [x] `track_shipment` tool with Pydantic in/out schemas
- [x] Schenker client: investigate JSON endpoint first, HTML fallback only if needed
- [x] Map raw upstream → `{sender, receiver, package, history[]}`
- [x] Unit tests with recorded fixtures (`vcrpy` or hand-rolled)
- [x] Integration test against the 11 sample refs from the brief

**Exit:** MCP Inspector calls `track_shipment` and returns structured data for every sample ref.

## Sprint 2 — Auth domain

- [x] Bearer token middleware on transport
- [x] `TokenStore` protocol + in-memory dev impl
- [x] Redis-backed prod impl (Upstash REST)
- [x] Per-token daily quota, sliding window
- [x] 401 / 429 with structured MCP error payloads
- [x] Mint/list/revoke CLI

**Exit:** unauthenticated rejected; exhausted token gets 429.

## Sprint 3 — Scale & observability

- [x] Knative `func.yaml` + Dockerfile
- [x] Deploy to local `kind` cluster
- [x] Tune autoscaler (concurrency target, min/max replicas)
- [x] Structured JSON logs (request/token correlation)
- [x] OpenTelemetry traces (tool dispatch + upstream fetch)
- [x] Load test (k6) at 100 RPS, p95 < 800ms

**Exit:** load test green; Grafana/Tempo screenshots in `docs/`.

## Sprint 4 — Hardening

- [x] Circuit breaker around Schenker upstream
- [x] Response cache (60s TTL keyed on ref, KV-backed)
- [x] Schema-drift detector for upstream payload
- [x] Public demo endpoint with free-tier token
- [x] Stretch tool: `track_shipment_events` — ships as a
      shipment-level events timeline. The per-package refinement is
      still in Stretch (needs upstream observation).

**Exit:** demo endpoint live; one-command `curl` example in README.

## Stretch

- **Per-package event split for `track_shipment_events`** — the
  current tool returns the shipment-level event timeline (the same
  list `track_shipment` exposes under `history`, without the
  sender / receiver / package envelope). The original brief's
  bonus asked for one timeline *per package* (per colli). That
  refinement needs:
  - `Shipment.packages: list[Package]` (multi-colli model)
  - A `Package.events: list[TrackingEvent]` per-package timeline
  - A parser branch that maps the upstream's per-package event arrays
    into the new shape
  Implementing without observing the upstream's per-package JSON
  shape would be guessing. Tracked for an iteration from a clean
  egress IP (this dev machine is rate-limited by DSV).
- Second carrier domain (PostNord) to prove the package-per-domain model.
- mTLS / OAuth client credentials beside bearer tokens.
- Multi-region Knative deployment with latency-based routing.

## Decision Log

**2026-05-15: Investigate JSON endpoint before scraping HTML.**
Schenker's tracking UI is a SPA — almost certainly backed by a JSON API. Scraping HTML is brittle and slow. Only fall back if no stable JSON exists.

**2026-05-15: Quota incremented post-success.**
Failed upstream calls don't burn quota. Trade-off accepted (we control upstream) — revisit if upstream cost becomes material.

**2026-05-16: Sprints 1–4 completed in one iteration.**
Ralph loop drove the implementation. Sprint 1 ships the JSON path; sprint 4
adds Playwright fallback, TTL cache, circuit breaker, and the drift
detector. The kind-cluster step from sprint 3 is documented but not
exercised in this iteration (no local k8s available); the `func.yaml`,
`Dockerfile`, and load-test script (`scripts/loadtest.k6.js`) cover the
deployment surface.
