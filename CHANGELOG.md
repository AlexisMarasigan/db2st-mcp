# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html). Pre-1.0, breaking changes
land on `main` without a bump.

## [Unreleased]

### Added

- `.github/workflows/release.yml` — tagged release pipeline. Verifies
  the tag matches the `pyproject.toml` version, runs the full gate
  set (ruff, ruff-format, mypy strict, unit tests, verify-docs,
  bandit medium+), builds the wheel + sdist via `uv build`,
  generates SHA256SUMS, and creates a GitHub Release with auto
  notes + artefacts attached. `workflow_dispatch` lets a maintainer
  re-run for an existing tag.
- `MCP_ALLOWED_HOSTS` env var on the FastMCP transport — extends the
  SDK's `127.0.0.1:*` / `localhost:*` / `[::1]:*` default with the
  operator's production hostname(s). Comma-separated. Documented in
  `.env.example`, `docs/KNATIVE.md`, and `deploy/func.yaml`.
- `tests/e2e/test_http_serve.py` — spawns `db2st-mcp serve` as a
  real OS process, polls `/healthz`, hits `/mcp/` unauthenticated,
  asserts the structured 401 envelope, and tears down via SIGTERM.
- `tests/e2e/test_stdio_stdout_clean.py` — pins stdout cleanliness
  for the stdio MCP path at `LOG_LEVEL=info`.
- `tests/unit/domains/tracking/server/test_parser_helpers.py` — 45
  parametrised tests for `_decimal`, `_int`, `_str`, `_datetime`,
  `_classify`.
- `tests/unit/apps/server/test_transport_security.py` — pins the
  `MCP_ALLOWED_HOSTS` parsing (empty / single / multi / whitespace).
- `tests/unit/domains/tracking/server/test_schenker_client_base_url.py`
  — pins that `SCHENKER_BASE_URL` actually changes the client's
  base URL.
- `deploy/knative-serving.yaml` — minimal `KnativeServing` CR
  applied by the bootstrap script.
- `scripts/local-cluster.sh` — bootstraps a local `kind` + Knative
  cluster and runs `func deploy --build --push=false`.
- `.dockerignore` — trims Docker build context from 377 MB to 8.7 kB.
- `scripts/verify_docs.py` `check_inrepo_references_exist()` — flags
  doc-referenced paths that don't actually exist in the tree.
  Catches the cross-iteration class of bug that surfaced in iter 22.
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
- `configure_logging` was writing to `sys.stdout`. The stdio MCP
  transport requires stdout for JSON-RPC frames; at the production
  default `LOG_LEVEL=info` every boot log corrupted framing.
  Switched to `sys.stderr`. Pinned by
  `tests/e2e/test_stdio_stdout_clean.py`.
- `_cmd_stdio` called `asyncio.run(deps.aclose())` *after*
  `mcp.run(transport="stdio")` had already torn down its event loop,
  so cleanup silently never ran. Re-implemented around
  `mcp.run_stdio_async()` inside a single `asyncio.run()` with
  proper try/finally.
- `SCHENKER_BASE_URL` was documented in `.env.example` and read into
  `Settings` but `SchenkerClient` hardcoded `https://mydsv.dsv.com`.
  Now properly plumbed; default updated to the real upstream
  (the legacy host 302-redirects there anyway).
- `--report` pytest CLI flag was registered only inside
  `tests/e2e/conftest.py`, so `pytest --report tests/unit` failed
  with "unrecognized arguments". Hoisted registration to the root
  conftest.
- `docs/KNATIVE.md` referenced `deploy/knative-serving.yaml` and
  `scripts/local-cluster.sh`, neither of which existed. Created
  both as real, validated files.
- Doc drift: DOMAIN.md files referenced consolidated-away test
  filenames (test_auth.py, test_tracking.py — both consolidated
  into the single tests/integration/test_real_upstream.py). Verified
  via the new check_inrepo_references_exist rule.
- Stale "sprint 2 wires it" / "sprint 2 enhancement" docstrings
  removed from the auth middleware; replaced with the actual
  contract.

### Removed

- Initial TypeScript scaffold (`package.json` / `tsconfig.json`),
  replaced by the Python project before any code shipped.
- Dead `src/db2st_mcp/shared/http.py::upstream_client` — declared
  "domains use this instead of raw httpx" but never called by any
  domain. Tested-but-unused = dead. Module and its smoke test
  removed.

## Notes

The repo started life on 2026-05-15 and reached "sprints 1–4 complete"
status on 2026-05-16. Subsequent commits are quality, observability,
and onboarding polish rather than feature work.
