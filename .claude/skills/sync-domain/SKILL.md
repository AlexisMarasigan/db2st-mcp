---
name: sync-domain
description: Scan a domain's code, propose updates to its DOMAIN.md as a diff. Never auto-writes; output is a proposal the human accepts or rejects. Use when a domain has changed and its DOMAIN.md may be stale.
---

# sync-domain

Propose a `DOMAIN.md` update for a given domain by comparing the current doc to the code in that domain. Output is always a **diff proposal** — never a direct write.

## When to invoke

- After a non-trivial change to `src/db2st_mcp/domains/<name>/`.
- When reviewing a PR that touches a domain but leaves `DOMAIN.md` unchanged.
- Before opening a release PR, run against every domain.

## Arguments

```
/sync-domain <domain>     # e.g. /sync-domain tracking
/sync-domain --all        # iterate over every domains/* subdir
```

## What it does

1. Resolve the target domain path: `src/db2st_mcp/domains/<name>/`.
2. Scan exports:
   - Public symbols re-exported from `shared/__init__.py` and `server/__init__.py` (and `client/__init__.py` if present).
   - Pydantic models in `shared/schemas.py`.
   - Protocols in `shared/protocols.py`.
3. Identify patterns in use:
   - Direct imports from other domains (must match a documented dependency).
   - Imports from `shared/` (always allowed).
4. Check `pyproject.toml` / module-level dependencies against the **Dependencies on other domains** section of `DOMAIN.md`.
5. Compare extracted facts to the current `DOMAIN.md` text:
   - New public symbols? → propose adding to the "Public surface" table.
   - Removed symbols? → propose removing the row.
   - New cross-domain import? → propose adding to "Dependencies on other domains".
   - Errors raised by handlers? → propose updating the "Error mapping" table.
6. Emit a unified diff against `DOMAIN.md`. Do not write the file.
7. Print a short rationale per change so the human can accept/reject each block.

## Output shape

```
# sync-domain: tracking

Proposed changes to src/db2st_mcp/domains/tracking/DOMAIN.md:

diff --git a/.../DOMAIN.md b/.../DOMAIN.md
--- a/.../DOMAIN.md
+++ b/.../DOMAIN.md
@@
- | TrackingEvent | shared/schemas.py | Pydantic models. |
+ | TrackingEvent, ShipmentMetadata | shared/schemas.py | Pydantic models. |

Rationale:
- ShipmentMetadata was added in shared/schemas.py:62 but is not in DOMAIN.md.
```

## Boundaries

- **Never writes the file.** Always emits a proposal.
- **Never invents content** not derivable from code.
- **Never expands DOMAIN.md past 2 pages.** If the doc would grow past the cap, propose splitting the domain instead.
- Decision log entries are off-limits — those are human-authored.

## Failure modes

- Domain dir does not exist → exit with usage hint and the list of known domains.
- `DOMAIN.md` missing → propose creating one with the standard skeleton.
- Code lacks `shared/__init__.py` re-exports → flag a warning ("no public surface to scan") but still scan `*.py` for `__all__`.
