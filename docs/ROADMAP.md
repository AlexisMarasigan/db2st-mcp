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
- [x] Knative manifest + local-cluster bootstrap script
      (`deploy/knative-serving.yaml`, `scripts/local-cluster.sh`).
      Scripted but not yet executed against a real cluster — needs
      a host with `kind` / `kubectl` / `func` installed.
- [x] Autoscaler annotations on `func.yaml` (concurrency target 50,
      min 0, max 20). Real load-driven tuning is deferred to a
      cluster-ready run.
- [x] Structured JSON logs (request_id + token_id correlation via
      structlog contextvars; token binding lives in the auth
      middleware after iter 29's fix).
- [x] OpenTelemetry traces opt-in via `[otel]` extra + the
      `OTEL_EXPORTER_OTLP_ENDPOINT` env var. No-op when unset.
- [x] k6 load-test script in `scripts/loadtest.k6.js`. Not yet
      executed against a running server — same blocker as the
      cluster deploy.

**Exit:** load-test script + autoscaler annotations + structured logs
ship in this iteration; **real cluster execution + p95<800ms
validation are deferred until a cluster host is available**.

## Sprint 4 — Hardening

- [x] Circuit breaker around Schenker upstream
- [x] Response cache (60s TTL keyed on ref) — **in-memory `TTLCache`
      (`shared/cache.py`)**, not KV-backed. KV-backed cache that
      survives pod churn is deferred to the Stretch section.
- [x] Schema-drift detector for upstream payload (`shared/drift.py`).
- [ ] Public demo endpoint with free-tier token. Deferred — needs a
      hosting environment to deploy into. Tracked in Stretch.
- [x] Stretch tool: `track_shipment_events` — ships as a
      shipment-level events timeline. The per-package refinement is
      still in Stretch (needs upstream observation).

**Exit:** circuit breaker + in-memory cache + drift detector + events
tool live. Public demo endpoint deferred until a hosting target is
chosen.

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

**2026-05-16: Stretch tool was briefly mis-marked as done, then actually shipped.**
The `track_shipment_events` stretch box was bulk-checked during the
initial roadmap walk-through without an implementation behind it.
Iter 55 caught the lie and unchecked it; iter 56 actually shipped the
shipment-level form (the events timeline only, no sender/receiver/
package envelope). The per-package split remains a real Stretch item
— deferred until a clean egress IP can observe the upstream's
per-package JSON shape.
