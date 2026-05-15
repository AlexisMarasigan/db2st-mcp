# CLAUDE.md

Entry point for AI coding assistants working in this repo. Read this first.

## What this repo is

A Python MCP (Model Context Protocol) server that exposes shipment tracking as authenticated tools. Built for horizontal scale, deployed as a Knative Function. See [ARCHITECTURE.md](ARCHITECTURE.md) for the 10,000 ft view.

## Navigation rules

This codebase follows the **Clara Philosophy**. To understand any part of it, load docs from root to leaf:

| Working on… | Load… |
|---|---|
| System-level reasoning | `ARCHITECTURE.md` |
| Routing / composition / middleware | `ARCHITECTURE.md` → `src/db2st_mcp/apps/server/APP.md` |
| Tracking behavior | `ARCHITECTURE.md` → `src/db2st_mcp/domains/tracking/DOMAIN.md` |
| Auth / quota behavior | `ARCHITECTURE.md` → `src/db2st_mcp/domains/auth/DOMAIN.md` |
| Deployment | `docs/KNATIVE.md` |
| Roadmap / sprint plan | `docs/ROADMAP.md` |

Each doc is capped (~1 page for ARCHITECTURE/APP, 1–2 for DOMAIN). Don't bloat them.

## Layout

```
src/db2st_mcp/
  apps/server/          # Composes domains. No business logic.
  domains/
    tracking/           # Schenker shipment tracking
      shared/           # Schemas, contracts, constants
      server/           # Handlers, services
      DOMAIN.md
    auth/               # Tokens, quotas
      shared/
      server/
      DOMAIN.md
  shared/               # Cross-cutting infra. Never imports from domains.
tests/
  unit/                 # Mirrors src/ layout
  integration/          # Hits Schenker upstream (sample refs)
  e2e/                  # Full server + MCP client
.claude/
  skills/sync-domain/   # Propose doc updates from code
  skills/verify-docs/   # Check docs vs code, report drift
```

## Maintenance rules

1. **shared/ is one-way.** Domains and apps import from `shared/`. Never the reverse.
2. **Domains are self-contained.** Cross-domain imports must be directional and documented in the dependent domain's `DOMAIN.md`.
3. **One page rule.** ARCHITECTURE.md ≤ 1 page. APP.md ≤ 1 page. DOMAIN.md ≤ 2 pages. If a doc grows past, split or simplify the system.
4. **Decision log at the bottom of every doc.** Every non-obvious choice gets one line + reason.
5. **If it's obvious from the code, don't document it.**
6. **Tests mirror src layout.** Touching `domains/tracking/server/foo.py` ⇒ tests at `tests/unit/domains/tracking/server/test_foo.py`.
7. **Conventional Commits.** `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`, `release:`. Optional scope: `feat(tracking): ...`.

## Engineering posture

- Sustainable over expedient. No quick hacks. Migrate, refactor, preserve behavior.
- TDD: write the failing test first.
- ≥80% coverage. Coverage gate enforced in CI.
- Type-strict (mypy strict mode). Pydantic for boundaries.

## Available project skills

Run these from inside the repo:

| Skill | Purpose |
|---|---|
| `.claude/skills/sync-domain` | Scan a domain's code, propose doc updates (diff only — never auto-write). |
| `.claude/skills/verify-docs` | Compare docs to code. Report drift. No automatic fixes. |

## Tools you should reach for

- `uv` — deps + venv. Never `pip install` directly.
- `ruff` — lint + format. One tool, both jobs.
- `mypy` — strict typing. New code must pass.
- `pytest` — all tests. Coverage via `pytest-cov`.
- `pre-commit` — runs locally before commit.

## What not to do

- Don't add a global state store. State belongs to a domain or to `shared/` if cross-cutting and stateless.
- Don't put business logic in `apps/server/`. It only wires.
- Don't import a domain from `shared/`.
- Don't bypass `pyproject.toml` deps with ad-hoc installs.
- Don't skip the failing-test step.
