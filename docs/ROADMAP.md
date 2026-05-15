# Roadmap

Phased plan. Each sprint ends with a runnable, demonstrable artifact.

## Sprint 0 — Foundations (current)

- [x] Repo skeleton + Clara-style docs
- [x] CLAUDE.md AI entry
- [ ] Python project scaffold (`pyproject.toml`, `src/` layout, domain stubs)
- [ ] CI: lint, typecheck, unit tests
- [ ] Pre-commit hooks

**Exit:** `uv sync && uv run pytest` passes against domain stubs.

## Sprint 1 — Tracking domain

- [ ] MCP server (Streamable HTTP transport) in `apps/server`
- [ ] `track_shipment` tool with Pydantic in/out schemas
- [ ] Schenker client: investigate JSON endpoint first, HTML fallback only if needed
- [ ] Map raw upstream → `{sender, receiver, package, history[]}`
- [ ] Unit tests with recorded fixtures (`vcrpy` or hand-rolled)
- [ ] Integration test against the 11 sample refs from the brief

**Exit:** MCP Inspector calls `track_shipment` and returns structured data for every sample ref.

## Sprint 2 — Auth domain

- [ ] Bearer token middleware on transport
- [ ] `TokenStore` protocol + in-memory dev impl
- [ ] Redis-backed prod impl (Upstash REST)
- [ ] Per-token daily quota, sliding window
- [ ] 401 / 429 with structured MCP error payloads
- [ ] Mint/list/revoke CLI

**Exit:** unauthenticated rejected; exhausted token gets 429.

## Sprint 3 — Scale & observability

- [ ] Knative `func.yaml` + Dockerfile
- [ ] Deploy to local `kind` cluster
- [ ] Tune autoscaler (concurrency target, min/max replicas)
- [ ] Structured JSON logs (request/token correlation)
- [ ] OpenTelemetry traces (tool dispatch + upstream fetch)
- [ ] Load test (k6) at 100 RPS, p95 < 800ms

**Exit:** load test green; Grafana/Tempo screenshots in `docs/`.

## Sprint 4 — Hardening

- [ ] Circuit breaker around Schenker upstream
- [ ] Response cache (60s TTL keyed on ref, KV-backed)
- [ ] Schema-drift detector for upstream payload
- [ ] Public demo endpoint with free-tier token
- [ ] Stretch tool: `track_shipment_events` (per-package events)

**Exit:** demo endpoint live; one-command `curl` example in README.

## Stretch

- Second carrier domain (PostNord) to prove the package-per-domain model.
- mTLS / OAuth client credentials beside bearer tokens.
- Multi-region Knative deployment with latency-based routing.

## Decision Log

**2026-05-15: Investigate JSON endpoint before scraping HTML.**
Schenker's tracking UI is a SPA — almost certainly backed by a JSON API. Scraping HTML is brittle and slow. Only fall back if no stable JSON exists.

**2026-05-15: Quota incremented post-success.**
Failed upstream calls don't burn quota. Trade-off accepted (we control upstream) — revisit if upstream cost becomes material.
