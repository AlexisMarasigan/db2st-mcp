# Roadmap

Phased plan. Each sprint ends with a runnable, demonstrable artifact.

## Sprint 0 — Foundations

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
- [x] Unit tests with hand-rolled JSON fixtures + `respx` for httpx
      transport mocking. (Sprint-1 plan listed `vcrpy` as an option;
      we ended up not needing recorded HTTP cassettes — every
      upstream interaction is small enough to fixture directly. The
      `vcrpy` dev dep was dropped in iter 97.)
- [x] Integration test against the 11 sample refs from the brief

**Exit:** MCP Inspector calls `track_shipment` and returns structured data for sample refs that the upstream resolves (some are rate-limited from any given dev IP — see `docs/UPSTREAM.md`). Sprint 4 added `track_shipment_events` as a second tool over the same orchestrator.

## Sprint 2 — Auth domain

- [x] Bearer token middleware on transport
- [x] `TokenStore` protocol + in-memory dev impl
- [x] Redis-backed prod impl (Upstash REST)
- [x] Per-token daily quota, UTC calendar-day (hard reset at 00:00 UTC)
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
- [x] Response cache (60s TTL keyed on ref). Two backends, picked by
      `RESPONSE_CACHE_BACKEND`:
      - `memory` (default): in-process `TTLCache` (`shared/cache.py`),
        per-pod, lost on restart.
      - `upstash`: `UpstashCache` (`shared/upstash_cache.py`), shared
        across pods, server-side TTL via `SET ... EX <seconds>`, so a
        cache entry survives pod churn up to the TTL. Uses the same
        Upstash credentials as `token_store=upstash` but is opt-in
        independently.
- [x] Schema-drift detector for upstream payload (`shared/drift.py`).
- [ ] Public demo endpoint with free-tier token. Deferred — needs a
      hosting environment to deploy into. Tracked in Stretch.
- [x] Stretch tool: `track_shipment_events` — ships as a
      shipment-level events timeline. The per-package refinement is
      still in Stretch (needs upstream observation).

**Exit:** circuit breaker + cache (memory + KV-backed) + drift
detector + events tool live. Public demo endpoint deferred until a
hosting target is chosen.

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
- Per-IP rate limit on auth failures (defense-in-depth). The
  current threat model relies entirely on secret entropy (2^256
  keyspace) to resist brute force — adequate but worth an IP-level
  guard so attackers can't even mount a guessing campaign.
- **Public demo endpoint with a free-tier token** (deferred from
  Sprint 4). Needs a hosting target — viable free-tier options
  worth evaluating:
  - Fly.io: native Docker, scale-to-zero, free vCPU + storage.
    `deploy/Dockerfile` builds cleanly; `flyctl deploy` would
    suffice once `MCP_ALLOWED_HOSTS`, `TOKEN_STORE=upstash`, and
    Upstash creds are set as secrets.
  - Railway / Render: same shape, push-to-deploy from GitHub.
  - GCP Cloud Run: closest to the Knative target (same autoscaler
    semantics), free tier covers occasional demo traffic.
  Any of those need a single mint-and-publicly-publish dev token
  with a low `daily_limit` (e.g., 100) so the demo can't be
  abused into a rate-limit drain on the upstream.

## Decision Log

**2026-05-15: Investigate JSON endpoint before scraping HTML.**
Schenker's tracking UI is a SPA — almost certainly backed by a JSON API. Scraping HTML is brittle and slow. Only fall back if no stable JSON exists.

**2026-05-15: Quota consumed pre-handler.**
Atomic Redis `INCR` is the only race-free option without a multi-step
compare-and-set. Failed upstream calls therefore burn one quota unit;
the alternative (decrement-on-success) needs a refund mechanism that
survives a crashed pod, which is more complexity than the dev box can
justify today. Revisit if upstream cost becomes material — see
`bearer_auth_middleware` for the implementation note.

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

**2026-05-16: KV-backed response cache promoted from Stretch into Sprint 4.**
Iter 78's honesty audit flagged the original `[x]` on "Response cache
(KV-backed)" because the implementation was in-memory `TTLCache` only.
Iter 80 added `shared/upstash_cache.py` — a generic Upstash-Redis-
backed cache with injectable codec — and wired
`RESPONSE_CACHE_BACKEND=upstash` through `build_deps`. Both backends
satisfy the existing `_Cache` Protocol used by `TrackingService`, so
no domain code changed. Pinned by 10 new unit tests on the cache
itself plus a `build_deps` branch test.
