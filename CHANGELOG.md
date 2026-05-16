# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html). Pre-1.0, breaking changes
land on `main` without a bump.

## [Unreleased]

### Added

- `tests/integration/test_real_upstream.py` parametrising the 11 sample
  references from the original brief through the real `TrackingService`.
  Marked `integration` and deselected by default; opt in with
  `pytest -m integration`. Nightly job in
  `.github/workflows/e2e.yml`.
- `tests/unit/apps/server/test_request_id_middleware.py` — 4 tests
  pinning UUID generation, header preservation, and contextvars
  binding for the request-id middleware.
- `docker` CI job (`.github/workflows/ci.yml`) that builds
  `deploy/Dockerfile`, runs the container, polls `/healthz`, and
  asserts HTTP 200.
- `LICENSE`, `SECURITY.md`, and this `CHANGELOG.md`.
- `scripts/example_call.py` — runnable demo client showing the JSON-RPC
  handshake plus a real `tools/call`. Unit-tested.
- `scripts/sync_domain.py` — executable counterpart to the
  `.claude/skills/sync-domain` prose spec. Proposes `DOMAIN.md` additions
  from `__all__` re-exports + cross-domain imports. Read-only.
- `scripts/verify_docs.py` — executable Clara-invariant enforcer wired
  into a new `verify-docs` job in `.github/workflows/ci.yml`. Checks:
  shared/ one-way rule, doc length caps, Decision Log presence,
  cross-domain import documentation, public-surface coverage.
- Real-subprocess E2E in `tests/e2e/test_mcp_stdio.py` covering
  `initialize`, `tools/list`, and `tools/call`.
- HTTP `/mcp/` integration test in
  `tests/unit/apps/server/test_http_transport.py`.
- Playwright HTML fallback when `DB2ST_HTML_FALLBACK=1`
  (`src/db2st_mcp/domains/tracking/server/html_fallback.py`), including
  detection of the SPA "Shipment not found" marker.
- Response cache, circuit breaker, and schema-drift detector under
  `src/db2st_mcp/shared/`.
- Upstash-Redis-backed token store (`[redis]` extra) with a fake-Redis
  unit test.
- Bearer-token auth middleware wired into the FastAPI app, plus
  `db2st-mcp mint / tokens list / tokens revoke` CLI subcommands.
- OpenTelemetry opt-in instrumentation (`[otel]` extra) and a
  request-id correlation middleware.
- k6 load-test script (`scripts/loadtest.k6.js`).
- Bandit static security scan as a CI job.

### Changed

- Composed the MCP transport's session-manager lifespan into the parent
  FastAPI app's lifespan. Without this, any HTTP request to `/mcp/`
  crashed with `Task group is not initialized` on first request — caught
  by the new HTTP integration test.
- DOMAIN.md files updated to match actual public surface
  (`SchenkerClient.resolve` / `.fetch_detail` instead of the previously
  documented `.fetch`).
- Tooling: pre-commit `ruff` hook bumped to v0.15.13; project mypy is
  CI-only (pre-commit's isolated env can't see optional/test deps).
- `mypy --strict` is green across the codebase (was 17 errors).

### Fixed

- Lifespan composition bug above (production HTTP transport path).
- `SchenkerClient.fetch_detail` now raises `ParseError` if the upstream
  payload isn't an object, matching the parser's contract.
- `PlaywrightHtmlFallback` now raises `NotFoundError` on the SPA's
  "Shipment not found!" marker instead of returning a misleading
  "scraped" event.
- `deploy/Dockerfile` was completely broken — missing `uv.lock` COPY
  plus the project itself was never installed in the runtime image
  (`ModuleNotFoundError: No module named 'db2st_mcp'`). Rebuilt around
  `uv build --wheel` + `pip install --prefix=/install` so the runtime
  stage gets a clean relocatable tree. Smoke-verified by the new
  `docker` CI job.
- CLI subcommands (`mint`, `tokens list`, `tokens revoke`) leaked the
  `SchenkerClient`'s httpx.AsyncClient — `AppDeps` was never closed.
  Each command now wraps its work in try/finally with
  `await deps.aclose()`.
- README's "Use as a deployed MCP" `curl` example was missing
  `Accept: application/json, text/event-stream`. Streamable HTTP
  rejected the request before tool dispatch.
- README Quickstart claimed `pytest` covers integration tests; the
  default now passes `-m "not integration"`, so the Quickstart now
  also documents the opt-in `-m integration` command.
- `deploy/func.yaml` `REPLACE_ME` placeholders now have a header
  comment that explains exactly what to substitute.

### Removed

- Initial TypeScript scaffold (`package.json` / `tsconfig.json`),
  replaced by the Python project before any code shipped.

## Notes

The repo started life on 2026-05-15 and reached "sprints 1–4 complete"
status on 2026-05-16. Subsequent commits are quality, observability,
and onboarding polish rather than feature work.
