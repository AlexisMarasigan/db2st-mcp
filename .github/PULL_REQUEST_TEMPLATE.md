# Pull request

## What changed

<!-- One or two sentences. Why this PR exists; the "what" should be obvious from the diff. -->

## Linked issue / context

<!-- Closes #123 / refs #456 / N/A -->

## Checklist

- [ ] Conventional commit prefix (`feat:` / `fix:` / `chore:` / `docs:` / `refactor:` / `test:` / `release:`)
- [ ] Tests added / updated for the change (unit, integration, or E2E — whichever fits)
- [ ] `uv run ruff check .` clean
- [ ] `uv run mypy` clean
- [ ] `uv run python scripts/verify_docs.py` clean
- [ ] If a domain changed: `DOMAIN.md` Public surface + Decision Log updated
- [ ] If the upstream contract changed: `docs/UPSTREAM.md` + parser fixtures updated
- [ ] If a CLI / public surface changed: README updated
- [ ] No secrets added (gitleaks runs on CI)

## Test plan

<!-- How did you verify? Paste the exact commands or screenshots. -->

## Risk notes

<!-- Anything reviewers should know: blast radius, rollback plan, feature flags, etc. Leave blank if low-risk. -->
