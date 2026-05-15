---
name: verify-docs
description: Verify CLAUDE.md / ARCHITECTURE.md / APP.md / DOMAIN.md against the code and report drift. Read-only. Use before opening a PR or as a pre-merge gate.
---

# verify-docs

Walks every doc in the repo and compares it to the code. **Read-only** — emits a report; never modifies files.

## When to invoke

- Pre-merge gate on every PR.
- Before tagging a release.
- After large refactors.

## What it checks

1. **Dependencies declared in DOMAIN.md match imports.**
   - Parse each domain's `DOMAIN.md` "Dependencies on other domains" section.
   - Walk Python imports in `src/db2st_mcp/domains/<name>/`.
   - Flag: undeclared imports, declared-but-unused dependencies.

2. **Contracts in DOMAIN.md match Pydantic models.**
   - Parse the "Contracts" block of `DOMAIN.md`.
   - Compare model names + field names against `shared/schemas.py`.
   - Flag: model renamed, field added/removed, type narrowed.

3. **Public surface matches `__all__` and re-exports.**
   - For each row in the "Public surface" table, verify the symbol is exported.
   - Flag: symbol missing or no longer exported.

4. **Clara invariants.**
   - `shared/` (process-wide) does not import from `domains/` or `apps/`.
   - No domain imports from another domain except via that domain's `shared/`.
   - No circular domain dependencies.

5. **Doc length caps.**
   - `ARCHITECTURE.md` ≤ ~1 page (220 lines).
   - `APP.md` ≤ ~1 page (220 lines).
   - `DOMAIN.md` ≤ ~2 pages (440 lines).
   - Flag: doc exceeds cap.

6. **Decision log presence.**
   - Every doc ends with a `## Decision Log` section.
   - At least one entry per non-trivial change in the last 50 commits touching the doc's directory.

## Output

A Markdown report grouped by file:

```
# verify-docs report — 2026-05-16T08:00:00Z

## src/db2st_mcp/domains/tracking/DOMAIN.md
- ⚠ MEDIUM: `ShipmentMetadata` added in shared/schemas.py:62 but missing from "Public surface".
- ✓ Dependencies match.
- ✓ Length under cap (148 lines).

## src/db2st_mcp/shared/
- 🔴 CRITICAL: src/db2st_mcp/shared/foo.py imports `db2st_mcp.domains.tracking.shared`.
  Clara invariant violated: shared/ must not import from domains/.

## Summary
- Files checked: 12
- Critical: 1
- Warnings: 1
- OK: 10
- Exit code: 1
```

Exit code: `0` if no critical issues, `1` otherwise.

## Boundaries

- **Never modifies files.** Report only.
- **Never auto-creates a Decision Log entry.** Flag missing entries; the human writes them.
- Trust the code as the source of truth for facts. Trust the doc for *rationale*.

## Failure modes

- Doc parse failure → flag as `parse_error` and continue.
- Code import cycle detected → flag as critical, abort further analysis for that domain.
