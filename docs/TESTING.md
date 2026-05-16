# Testing

## Layout

```
tests/
├── unit/         # Fast, isolated, ~150 tests. Mirrors src/ layout.
├── integration/  # Hits live DSV upstream. Deselected by default.
└── e2e/          # Real-process tests (db2st-mcp stdio / serve subprocesses).
```

## Running locally

```bash
# Unit suite (default — `-m "not integration"` is in addopts).
uv run pytest

# Just unit (excludes e2e).
uv run pytest tests/unit

# E2E — exercises stdio + HTTP serve as real subprocesses.
uv run pytest tests/e2e --report   # writes docs/E2E-REPORT.md

# Live upstream — only from an IP that isn't rate-limited by DSV.
uv run pytest -m integration
```

## Coverage

Gate is 80% on the unit suite (`addopts: --cov-fail-under=80`). Current
coverage is ~87%. The `--cov*` flags are baked into `addopts`; you can
opt out for a faster run with `--no-cov` on the command line.

## `pytest -W error` mode

Useful for hunting deprecation warnings, but expect one known false
positive when the full unit suite runs together:

```
PytestUnraisableExceptionWarning: Exception ignored in:
<function BaseEventLoop.__del__ at 0x…>
```

Source: pytest-asyncio creates a fresh event loop per async test;
Python's GC sometimes finalises an old loop on a *later* test
boundary, which pytest's unraisable hook captures and reports. The
loops themselves close cleanly inside their owning tests
(verified iter 35 via per-directory bisection); the GC timing is
the source of the warning, not a real resource leak.

This warning category is therefore allowed in normal runs and only
surfaces under `-W error`. If you want to suppress it manually:

```bash
uv run pytest -W error -W default::pytest.PytestUnraisableExceptionWarning
```

## What CI runs

- `.github/workflows/ci.yml` — lint, format check, mypy strict,
  unit tests on py3.12 + py3.13, verify-docs, wheel build, Docker
  build + container smoke.
- `.github/workflows/e2e.yml` — E2E suite on PRs (with PR comment),
  nightly real-upstream integration job (continue-on-error, since
  upstream rate-limiting is outside our control).
- `.github/workflows/security.yml` — bandit (zero findings at every
  severity), pip-audit, gitleaks, CodeQL.
- `.github/workflows/release.yml` — pre-release gates (lint + type
  + tests + verify-docs + bandit) before building the wheel and
  publishing the GitHub Release on a `v*.*.*` tag.

## Test isolation rules

- Tests must mirror `src/` layout (`tests/unit/foo/test_bar.py`).
- A new domain gets a new `tests/unit/domains/<name>/` tree.
- Network is forbidden in unit + e2e tests; live upstream lives in
  `tests/integration/` only.
- Each test gets fresh app state (`build_app()` fixture pattern);
  the MCP session manager is single-use per instance.
