# Contributing

> Read [CLAUDE.md](CLAUDE.md) first. It is the navigation primer; this file is the workflow primer.

## Setup

```bash
uv sync --group dev          # install + dev tooling
uv run pre-commit install    # local hooks
cp .env.example .env         # adjust as needed
```

## Workflow

1. **Branch.** `feat/<scope>-<short-desc>` or `fix/<scope>-<short-desc>`.
2. **Write the failing test first.** No exceptions. TDD is enforced by CI's coverage gate (80%).
3. **Implement minimally** to make the test pass.
4. **Refactor** without breaking tests.
5. **Run locally** before pushing:
   ```bash
   uv run ruff check .
   uv run ruff format .
   uv run mypy
   uv run pytest
   ```
6. **Open a PR.** CI will run lint, typecheck, tests on py3.12 + py3.13, E2E (writes `docs/E2E-REPORT.md`), and security scans.

## Commit messages

Conventional Commits. Scope optional.

| Prefix | For |
|---|---|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `chore:` | Deps, CI, build, config |
| `refactor:` | Internal restructure, no behavior change |
| `docs:` | Documentation |
| `test:` | Tests |
| `release:` | Auto-generated version bumps |

Examples:
- `feat(tracking): add SchenkerClient with httpx-based fetch`
- `fix(auth): correct UTC day boundary in quota consume`
- `docs(architecture): clarify domain dependency rule`

## Documentation rules

- **shared/ never imports from domains/ or apps/.** CI does not yet enforce this mechanically (see `verify-docs` skill); reviewers must.
- Update the matching `DOMAIN.md` / `APP.md` in the same PR as code changes.
- Add a line to the file's **Decision Log** when a choice is non-obvious or reverses an earlier one.
- One-page caps: `ARCHITECTURE.md` ≤ 1 page, `APP.md` ≤ 1 page, `DOMAIN.md` ≤ 2 pages.

## Adding a new domain

1. Create `src/db2st_mcp/domains/<name>/` with `shared/` and `server/` (and `client/` if applicable).
2. Add `DOMAIN.md` describing the capability, public surface, contracts, and dependencies.
3. Add tests under `tests/unit/domains/<name>/` mirroring the source layout.
4. Add an entry to `ARCHITECTURE.md`'s domain table.
5. If the new domain depends on an existing one, document the direction in its `DOMAIN.md`.

## Adding a new tool

1. Live in the relevant domain's `server/` (or create a new domain).
2. Input/output schema as Pydantic models in `shared/schemas.py`.
3. Tool registered in `apps/server/main.py` (no business logic there).
4. Unit tests for the handler. Integration tests if it calls a real upstream.

## Releases

Cut a release by tagging a commit with `vMAJOR.MINOR.PATCH` matching the
`version` field in `pyproject.toml`:

```bash
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

`.github/workflows/release.yml` (a) verifies the tag matches the pyproject
version, (b) builds the wheel + sdist via `uv build`, (c) generates
SHA256 checksums, and (d) creates a GitHub Release with auto-generated
release notes and the artefacts attached.

Re-running for a previously-pushed tag works too — kick it manually
from the Actions tab via `workflow_dispatch`.
