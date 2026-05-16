# Security Policy

## Supported versions

This project is pre-1.0. Security fixes are landed on `main`; there are no
LTS branches yet.

| Version | Supported |
|---|---|
| 0.0.x | ✓ |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, email **dev@talendary.com** with:

- A description of the issue and its impact.
- Steps to reproduce (PoC welcome, sanitised credentials only).
- Affected commit / version.
- Your suggested fix or mitigation, if any.

You should receive a first response within 72 hours. If you have not heard
back in five working days, please re-send.

## What's in scope

- Anything in `src/db2st_mcp/` — auth middleware, token store, MCP transport
  glue, upstream client, parser.
- The Knative deployment manifests (`deploy/`).
- CI workflows (`.github/workflows/`).

## What's out of scope

- The upstream DSV / DB Schenker public tracking API.
- Third-party dependencies (please report those upstream).
- Findings that require a compromised local environment (e.g., already
  read access to `.env` or the host's secret store).

## What we ship to mitigate common risks

- **Token storage**: only SHA-256 hashes of bearer secrets are persisted
  (`src/db2st_mcp/domains/auth/`). Raw secrets are surfaced once at mint
  time and never again.
- **Quota gate**: per-token daily limits cap blast radius for stolen tokens.
- **Input validation**: every MCP tool argument is a Pydantic model with
  bounded field constraints (length, type).
- **Static analysis**: `mypy --strict`, `bandit -ll`, `ruff`, `pip-audit`,
  `gitleaks`, and CodeQL run on every PR (see `.github/workflows/`).
- **Transport-layer hardening**: the MCP SDK's DNS-rebinding protection is
  on by default.

## Coordinated disclosure

We follow a 90-day disclosure window unless a longer window is mutually
agreed for fix coordination.
