# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/spec/v2.0.0.html). Pre-1.0, breaking changes
land on `main` without a bump.

## [Unreleased]

### Fixed

- **Wired the schema-drift detector into the upstream client**
  (`shared/drift.py`). Sprint 4 listed it `[x]` and the module
  shipped with unit tests, but `grep -rn "from db2st_mcp.shared.drift"
  src/` returned nothing — the detector was dead code from a
  runtime standpoint. Now called from both `SchenkerClient.resolve()`
  (`drift_check("resolver", payload)`) and `fetch_detail()`
  (`drift_check(f"detail:{type_hint}", payload)`); the per-mode
  key lets drift dashboards split shipment types so a schema
  change in `land` doesn't silently obscure one in `ocean`. Pinned
  by a respx-based integration test.

### Changed

- **README local-MCP Quickstart now enables the HTML fallback**
  (`-e DB2ST_HTML_FALLBACK=1` + `--extra fallback` +
  `playwright install chromium`). Without the fallback, new users
  on a fresh egress IP hit "shipment not found" on every call —
  not because anything is broken, but because the upstream JSON
  path rate-limits fresh IPs. Doc-side fix for iter-100's
  real-time discovery.
- Dropped the dead `shared/logging.get_logger()` helper. Production
  code (17 call sites) uses `structlog.get_logger(__name__)`
  directly; the helper was only imported by its own smoke test.
  Third in the dead-code series after iter-105 (`store.py`
  `__all__`) and iter-106 (`tracking/shared/__init__.py`
  re-exports). Module docstring now spells out the canonical
  pattern so a future contributor doesn't re-add a wrapper.

### Observability

- **Structured log events on every auth-failure branch**
  (`auth.failure` with `reason=header_missing_or_malformed` /
  `token_unknown` / `token_revoked`). The wire response stays
  generic (iter-109 side-channel fix); the log line carries the
  distinction so ops dashboards can split 401s by cause without
  reaching past the trust boundary. The revoked-token event also
  logs `token_id` because that's actionable for an operator
  investigating a stuck client.
- **`auth.quota_exhausted` event on every 429** with `token_id`
  and `plan`. Mirrors the 401 pattern at the next-rung-up: an SRE
  seeing rising 429s can identify abusive callers immediately. The
  `plan` field is included because free vs. pro quota patterns are
  operationally distinct.
- **`circuit_breaker.opened` / `circuit_breaker.closed`** events
  fired only on state transitions (not on every healthy request,
  which would drown ops). `opened` is `warning`-level with the
  failure-count + threshold + cooldown captured inline; `closed`
  is `info`-level (good news, signals upstream recovery).
- Per-domain Observability sections in `docs/AUTH.md` and
  `tracking/DOMAIN.md` catalogue every event name + its fields +
  when it fires. `ARCHITECTURE.md` gained a top-level
  Observability paragraph that names the `<domain>.<verb>` event
  convention, states the contextvars contract (`request_id`
  always; `token_id` + `plan` on authenticated requests), and
  links to both per-domain inventories.
- `auth/DOMAIN.md` Failure-modes table got a third column wiring
  each cause to its log event, plus a paragraph noting the 401
  response body is identical across all four branches by design
  (iter-109) — the log line is the only place the cause shows up.

### Internal

- **Test infrastructure consolidation** (iters 118–123). The iter-
  111-114 observability features each added a spy-the-`_log` test.
  Each test originally defined its own local `_SpyLogger` class
  and called `monkeypatch.setattr` inline (or, in the breaker
  case, swapped the module-level `_log` with `try/finally`). Over
  six iterations the pattern was extracted into:
  - `SpyLogger` class in `tests/conftest.py` covering `info`,
    `warning`, and `exception` levels with a uniform
    `(event_name, kwargs)` capture shape.
  - Per-test-file `spy_log` fixtures (one per module-under-test;
    a fixture-factory was rejected as more indirection than three
    callers warrant) that `monkeypatch.setattr` the target
    module's `_log` to a `SpyLogger()` and rely on pytest's
    automatic teardown.
  - Strengthened `test_route_exception_propagates_via_500` to
    assert the `request.failed` log line is actually emitted, not
    just that the 500 status surfaces — without the assertion,
    removing the `_log.exception(...)` call would have left the
    test green.

### Security

- **Closed an auth-response side channel.** Three branches of
  `bearer_auth_middleware.authenticate()` (missing `Authorization`
  header, wrong token, revoked token) returned the same
  `status_code` and `error` code but different `message` strings
  ("missing bearer token" vs "invalid token"). An attacker
  enumerating tokens could distinguish "no header" from "wrong
  token" by reading the response body. Collapsed all three onto
  a single `_AUTH_FAILURE_MSG = "missing or invalid bearer token"`
  constant; pinned by a new unit test
  (`test_auth_failure_message_is_identical_for_missing_and_invalid`)
  that asserts identicality across all three branches. The
  threat-model row in `docs/AUTH.md` previously promised this
  invariant ("Generic 401 for missing or invalid"); the code now
  matches the doc.
- Threat-model honesty pass on `docs/AUTH.md`: the brute-force row
  claimed `rate-limited 401`, but no per-IP rate limit exists in
  the middleware. The 2^256 keyspace makes brute force
  computationally absurd anyway, but promising a control we don't
  have is a security-doc lie. Rewrote the row to be honest and
  added a Stretch entry ("Per-IP rate limit on auth failures") so
  the defence-in-depth gap is tracked.

### Added

- **KV-backed response cache** (`shared/upstash_cache.py`). Generic on
  the cached value type, injectable encode/decode codec, server-side
  TTL via `SET ... EX <seconds>` so entries survive pod churn up to
  the TTL. Opt in with `RESPONSE_CACHE_BACKEND=upstash`; reuses the
  `UPSTASH_REDIS_REST_URL/_TOKEN` pair already used by the token
  store, but is enabled independently. The default
  (`RESPONSE_CACHE_BACKEND=memory`) keeps the previous in-process
  `TTLCache` behaviour. `RESPONSE_CACHE_TTL_SECONDS` is now a knob
  (defaults to 60). Promotes the "KV-backed cache" item from Stretch
  into a real Sprint 4 deliverable. Pinned by 10 cache-level unit
  tests + a `build_deps` branch test. Architecture / KNATIVE / AUTH
  / .env.example refreshed.

### Changed

- Dependabot now also watches the `Dockerfile` base image, in addition
  to `pip` and `github-actions`. Weekly cadence preserved.
- `tool.mypy.files` extended to include `scripts/` (was `src` + `tests`
  only). The three production-adjacent helper scripts that ship in the
  sdist — `verify_docs.py`, `sync_domain.py`, `example_call.py` — are
  now part of the strict-typecheck surface (84 source files, was 81).
- Dropped 4 dead dev deps (`vcrpy`, `hypothesis`, `pytest-httpx`,
  `types-requests`) — none imported anywhere in `src/`, `tests/`, or
  `scripts/`. Cuts dev install footprint, lock-file size,
  pip-audit surface, and Dependabot churn for zero loss.
- Added `playwright.*` to the existing `[[tool.mypy.overrides]]`
  with `ignore_missing_imports = true`, alongside `upstash_redis.*`
  and `opentelemetry.*`. Plugs a latent failure mode where mypy
  strict would reject `html_fallback.py`'s import-inside-try guard
  on any dev box that hadn't transitively pulled Playwright.
- CONTRIBUTING.md Setup now has an "Optional extras" subsection
  documenting the `redis` / `fallback` / `otel` extras with their
  trigger condition and exact install command. `uv sync --group dev`
  deliberately doesn't pull `[project.optional-dependencies]`; the
  doc table tells devs when they need to.
- **Deeper doc-vs-code audit pass** (iters 102–108). More substantive
  drift caught after the iter-84-95 sweep:
  - ROADMAP Sprint 1 listed `vcrpy or hand-rolled` for fixtures, but
    `vcrpy` was never imported and iter-97 removed it. Replaced with
    what actually shipped (hand-rolled JSON + `respx` for httpx
    transport mocking).
  - ROADMAP Sprint 2 + auth `DOMAIN.md` described the quota as a
    "sliding" / "rolling" window. The actual implementation is a UTC
    calendar-day counter (`quota:{token_id}:{YYYY-MM-DD}`) that
    hard-resets at 00:00 UTC. Operator-meaningful difference:
    rate-limited at 23:50 means rate-limited for ~10 minutes, not
    24h. Three doc spots corrected with an explicit 23:59→00:00
    example.
  - ROADMAP Sprint 0 still labelled `(current)`. Removed — the
    roadmap reads cleanest as a historical record now that Sprints
    1-4 are all done.
- **Dead-code cleanups.** Two unused re-export shells dropped after
  grep confirmed nobody imports through the package surface:
  - `domains/auth/server/store.py` imported `AuthContext` and
    `TokenStore` only to re-export them via `__all__`. Neither name
    is used elsewhere (`AuthContext` is constructed in the
    middleware; `TokenStore` is a Protocol that `InMemoryTokenStore`
    duck-types). Pared `__all__` to `["InMemoryTokenStore"]`.
  - `domains/tracking/shared/__init__.py` re-exported 5 schemas, but
    every one of the 14 in-tree consumers goes direct to
    `tracking.shared.schemas`. The re-export list was also stale
    (missing `ShipmentType`). Replaced with a docstring pointing at
    the submodule.

### Fixed

- **Deployment-breaking gap: `deploy/Dockerfile` didn't install the
  `[redis]` extra**, even though `deploy/func.yaml` defaults to
  `TOKEN_STORE=upstash` + `RESPONSE_CACHE_BACKEND=upstash` (both
  import `upstash_redis.asyncio` at runtime). A pod started from
  this image with the manifest unchanged would crash on the first
  authenticated request with `Db2stError: upstash-redis not
  installed`. Latent since the iter-14 Dockerfile rewrite. Fix is
  one flag: `uv export ... --extra redis`. The `[fallback]` and
  `[otel]` extras stay opt-in.
- **CI smoke gap that let the Dockerfile regression happen**: the
  Docker job only hit `/healthz` with `DB2ST_AUTH_DISABLED=1` — a
  path that never imports `upstash_redis`, so the missing `[redis]`
  extra was invisible to every CI run. Added a `docker exec ...
  python -c "from upstash_redis.asyncio import Redis"` inside the
  same smoke step. If the Dockerfile ever drops `--extra redis`
  again, CI catches it before the image lands anywhere.
- **Doc-vs-code audit sweep** (iters 84–95). Twelve substantive
  doc-vs-code drift bugs caught and corrected over a focused doc
  audit pass, with no code changes:
  - `docs/TESTING.md` undersold the suite ("~150 tests / ~87%
    coverage" → actually 199 / 95.51%). Refreshed.
  - `docs/AUTH.md`, `domains/auth/DOMAIN.md`, and `docs/ROADMAP.md`
    Decision Log all claimed quota was incremented *post-success*
    ("failed upstream calls don't burn budget"). The middleware
    actually `INCR`s **pre-handler** — a 5xx still costs one quota
    unit. Three copies of the same lie corrected; the canonical
    trade-off discussion now lives in one place (AUTH.md Decision
    Log) and the others link to it.
  - `APP.md` Files table listed a non-existent `routes.py`, missed
    `mcp_app.py` + `middleware.py`, and omitted `stdio` from the
    CLI subcommand list. Fixed.
  - `tracking/DOMAIN.md` Contracts block had drifted from
    `shared/schemas.py`: `PackageInfo.dimensions_cm` (a tuple) had
    long been replaced by separate `length_cm/width_cm/height_cm/
    volume_m3`; `Shipment` was missing the `type` and `source`
    fields that appear in the wire output; defaults were missing
    throughout. Resynced.
  - `docs/UPSTREAM.md` detail-endpoint table missed trailing
    slashes on four entries (`land_se`, `dsv`, `atol`, `cos`),
    listed an `air-ocean/search` endpoint the client never
    dispatches to, and omitted the `unknown` fallback. Synced to
    the actual `DETAIL_PATHS` map.
  - `ARCHITECTURE.md` Shared section claimed `shared/` housed an
    "HTTP client wrapper" (removed in iter 20) and omitted five
    Sprint-3/4 modules (`cache.py`, `upstash_cache.py`,
    `circuit_breaker.py`, `drift.py`, `observability.py`).
    Re-enumerated.
  - `CONTRIBUTING.md` "Adding a new tool" pointed at
    `apps/server/main.py` for tool registration (actually
    `mcp_app.py` since sprint 2) and `shared/schemas.py` for args
    schemas (actually the domain's `server/tool.py`). Two real
    lies a new contributor would have hit.
  - `APP.md` Boot order missed `TrackingService` + cache backend
    construction, collapsed middleware ordering into one line
    (the LIFO order matters — `request_id` binds contextvars
    before auth emits its first log line), and omitted
    `instrument_app(app)` entirely.
  - `APP.md` composition diagram described `/healthz` as
    "liveness + token-store ping" but the handler is pure
    liveness. Operationally meaningful — a Knative readiness
    probe against `/healthz` would not catch Upstash outages.
  - `tracking/DOMAIN.md` Error mapping table listed only "Upstream
    timeout / 5xx" for `UpstreamUnavailableError`, hiding the
    other four causes (429, other 4xx, connection errors, non-JSON
    body). Re-enumerated.
  - `docs/E2E-REPORT.md` duration figure was stale (0.1 → 0.2 min).
    Regenerated via the same `--report` flow CI uses.
- ROADMAP Sprint 3/4 had several `[x]` marks that overstated what
  shipped: cluster deploy, autoscaler tuning, and load-test execution
  (Sprint 3) all ship as scripts/manifests but were never executed
  against a real cluster; "Response cache (KV-backed)" was actually
  in-memory `TTLCache`; "Public demo endpoint" was never deployed.
  Rewritten with the concrete blocker captured inline and the Exit
  lines updated. Same honesty pattern as iter 55.
- `.gitignore` had a duplicate `dist/` entry (one near the top, one
  later); deduped.
- `docs/KNATIVE.md` had two stale claims that implied
  load-driven autoscaler tuning had happened. Reworded the
  Autoscaling-notes section to call out the values as reasoned
  defaults pending cluster execution, and added a 2026-05-16
  Decision Log entry stating that cluster execution + load-test +
  autoscaler tuning are deferred until a `kind`/`kubectl`/`func`-
  capable host is available. Same honesty pattern as iter 78's
  ROADMAP edit, applied at the deployment-doc layer.
- Bandit was emitting 9 spurious `Test in comment: <word> is not a
  test name or id, ignoring` WARNINGs every CI run. The cause:
  trailing rationale text after `# nosec BXXX` was being parsed as
  more test IDs. Moved the rationale to a preceding `#` comment
  block on 4 sites; dropped one stale `# nosec B104` annotation
  that bandit was reporting as unused. `Total potential issues
  skipped` 6 → 5; WARNINGs 9 → 0.
- The iter-80 KV-backed cache feature wired
  `RESPONSE_CACHE_BACKEND` through `Settings`, `build_deps`, and
  `.env.example`, but missed `deploy/func.yaml`. An operator
  running `func deploy` would have silently gotten the default
  per-pod memory cache — defeating the point of the KV-backed
  cache in a multi-pod deployment, where each pod would serve
  stale or empty results independently and burn upstream quota.
  Added `RESPONSE_CACHE_BACKEND=upstash` +
  `RESPONSE_CACHE_TTL_SECONDS=60` to `deploy/func.yaml`'s `envs`
  block (with a comment explaining why "memory" is wrong in a
  multi-pod context), and synced the `func.yaml` essentials
  snippet in `docs/KNATIVE.md`.

### Added

- `python -m db2st_mcp` invocation works alongside the `db2st-mcp`
  console script (new `__main__.py` re-exports `cli.main`). Pinned
  by a subprocess test. E2E tests + demo script now use the
  canonical shorter form.
- E2E live-subprocess test for `track_shipment_events` (full
  `tools/call` round-trip), plus the `tools/list` test now asserts
  both tools appear.
- `__init__.py` markers in every test directory under `tests/unit/`
  so pytest discovers each test as a fully-qualified package
  member. Prevents future basename collisions across domains.
- `pre-commit run --all-files` documented in CONTRIBUTING workflow
  as the one-shot alternative to per-file hooks.
- ROADMAP Decision Log entry capturing the iter-55/56 stretch-tool
  history (briefly mis-marked done → unchecked → actually shipped).
- **`track_shipment_events` MCP tool** (sprint 4 stretch from the
  original brief). Lighter shape than `track_shipment`: returns just
  the events timeline. Useful for poll-style clients that don't need
  the sender / receiver / package envelope. Per-package event split
  (one timeline per colli) is still in `Stretch` — needs observation
  of the upstream's per-package JSON shape.
- Surfaced the new tool across every user-facing doc: DOMAIN.md
  Public surface table, README's "Use as a local Claude Code MCP"
  table, README's deployed-MCP curl example (with a second `# 3b.`
  for the events tool), APP.md's composition diagram, CHANGELOG,
  decision-log entry in tracking/DOMAIN.md explaining why we
  shipped shipment-level instead of speculating per-package, and
  `scripts/example_call.py` (the demo now invokes both tools).
- Test coverage further pushed to **95.45%**:
  - `tool.py` 81.82% → 100% (whitespace-only reference guard).
  - `service.py` 75% → 87.5% (NotFoundError resets breaker;
    fallback engaged when breaker open + cache populated).
- `twine check --strict` runs on wheel + sdist in both the `build`
  CI job and the release `build-and-release` job. Catches malformed
  long_description, classifiers, or Project-URLs before any release
  uploads.
- `[project.urls]` extended to the PyPI-conventional set (Homepage,
  Documentation, Source, Changelog, Issues, Bug reports, Security).
- `[project.classifiers]` bumped to "4 - Beta" + Framework FastAPI,
  Intended Audience, Topic tags.
- Bandit scan extended to `scripts/` (verify_docs.py, sync_domain.py,
  example_call.py). All findings annotated with `# nosec BXXX` +
  rationale per project policy.
- `docs/TESTING.md` — unit/integration/e2e layout, coverage gate,
  `pytest -W error` caveat, CI workflow inventory, test-isolation
  rules. README links to it.
- Test-coverage push from ~88% to **94.27%**:
  - `apps/server/cli.py` 80.95% → 100% (`_cmd_serve` and `_cmd_stdio`
    dispatches now mock uvicorn / `run_stdio_async`).
  - `apps/server/dependencies.py` 76% → 100% (upstash branch + HTML
    fallback branch + graceful degradation when fallback missing).
  - `apps/server/main.py` 95.92% → 100% (`DB2ST_AUTH_DISABLED=1`).
  - `apps/server/mcp_app.py` 88.46% → 100% (registered tool body
    invoked via `mcp.call_tool`).
  - `apps/server/middleware.py` 83% → 100% (route-exception branch).
  - `domains/tracking/server/parser.py` 92% → 98.88% (7 defensive
    guards for nested malformed fields).
  - `domains/tracking/server/schenker_client.py` 83.51% → 97.94%
    (XSRF prime failure, timeout, network error, 4xx-other,
    non-JSON, empty resolver, context manager API).
  - `domains/auth/server/store.py` 93.62% → 97.87% (unknown-id
    consume → exhausted).
  - `domains/auth/server/upstash_store.py` 82.61% → 96.52%
    (corrupt-record paths, decode-record shapes, revoke-noop).
- New e2e tests:
  - `test_mcp_allowed_hosts.py` — `MCP_ALLOWED_HOSTS` widens the
    DNS-rebinding allowlist in a real subprocess (positive +
    negative-control).
  - `test_request_id_middleware.py` exception-branch test.
- Token-id correlation: `bearer_auth_middleware` now binds `token_id`
  and `plan` to structlog's contextvars on successful auth, so every
  log line in an authenticated request can be traced back to the
  caller. Regression-pinned by
  `test_middleware_binds_token_id_to_contextvars`.
- Parametrised dispatch-table test for `SchenkerClient.fetch_detail`
  covering every entry in `DETAIL_PATHS` (land, land_au, ocean, air,
  dsv, atol, cos, unknown).
- `test_fetch_detail_raises_parse_error_for_non_dict_payload` pins
  the iter-19 `ParseError` branch.
- `.github/workflows/release.yml` — tagged release pipeline. Verifies
  the tag matches the `pyproject.toml` version, runs the full gate
  set (ruff, ruff-format, mypy strict, unit tests, verify-docs,
  bandit at every severity), builds the wheel + sdist via `uv build`,
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
- Bandit static security scan as a CI job — gate at zero findings at
  every severity level; intentional exceptions carry a `# nosec BXXX`
  annotation with rationale.

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

- Pre-commit `check-yaml` hook silently rejected the project tree:
  - `deploy/knative-serving.yaml` is a multi-doc manifest;
    `check-yaml`'s default loader couldn't parse it. Fixed with
    `--allow-multiple-documents`.
  - `.github/workflows/ci.yml` had `name: Smoke: container boots
    + /healthz returns 200` — unquoted second `:` confused the
    strict loader. Quoted the value; added `--unsafe` for GHA's
    custom tags / `${{ … }}` expressions.
  - 6 test files had drifted from `ruff format` style. Reformatted.
- Sdist was packaging `.claude/ralph-loop.local.md` — local-only
  ephemeral state. Hatchling's default sdist includes any file not
  explicitly gitignored; the file's pattern wasn't covered. Added
  the conventional `*.local.*` rule to `.gitignore` so any future
  `<thing>.local.<ext>` is automatically excluded.
- CI `pip-audit` was silently scanning nothing because `uv export`'s
  `-e .` editable entry confused the action. Now filters editable +
  comment lines before passing requirements to pip-audit.
- CI docker smoke leaked containers on failure and couldn't survive
  re-runs (no `--rm`, no cleanup trap). Now uses `docker run --rm`
  with a `trap ... EXIT` that logs and stops on every exit path.
- CI e2e report + PR comment used the default `if: success()`, so
  the report wasn't uploaded on failure. Now `if: always()`.
- CI `verify-docs` job no longer runs `uv sync --frozen --group
  dev` for a pure-stdlib script. Saves ~30s on every PR.
- `parse_resolver` crashed with `AttributeError` on non-object / non-list
  payloads (None, scalar, string). Now raises `ParseError` consistent
  with the parser's contract; pinned by a parametrised test across
  None / int / str / float / bool.
- `main()` had a dead "unknown command" branch that argparse made
  unreachable (the parser already restricts `command` to the choices
  list). Removed; saves a coverage false-positive.
- Token-id was never reaching structlog contextvars. The previous
  `request_id_middleware` tried to read `request.state.auth` and bind
  `token_id` — but it ran outermost (added last in Starlette LIFO
  order), so `state.auth` was always None and the binding silently
  never happened. Every production log line was missing the caller
  correlation it was supposed to carry. Now `request_id_middleware`
  binds only `request_id` + `path`; `bearer_auth_middleware` binds
  `token_id` + `plan` after successful auth, where the timing is
  actually correct.
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
