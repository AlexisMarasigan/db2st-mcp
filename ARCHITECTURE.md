# Architecture

> 10,000 ft view. For app composition see [src/db2st_mcp/apps/server/APP.md](src/db2st_mcp/apps/server/APP.md). For domain detail, see each `DOMAIN.md`.

## What it is

A stateless HTTP service that speaks MCP (Streamable HTTP transport), authenticates callers via bearer token + per-token quota, and dispatches tool calls to domain handlers. The first domain is **tracking** (DB Schenker public tracking). Auth is its own domain. Deployable as a Knative Function.

## Golden path

```
HTTP request
  → apps/server         (transport, routing)
  → domains/auth        (validate token, decrement quota)
  → tool dispatcher     (apps/server)
  → domains/tracking    (call Schenker, parse, return structured result)
  → HTTP response
```

Every request follows this path. Everything else is supporting detail.

## Domains

| Domain | What it owns | DOMAIN.md |
|---|---|---|
| `tracking` | Shipment tracking. Schenker client. Tool handler. Parsing + schema. | [DOMAIN.md](src/db2st_mcp/domains/tracking/DOMAIN.md) |
| `auth` | Tokens, quotas, lifecycle. | [DOMAIN.md](src/db2st_mcp/domains/auth/DOMAIN.md) |

## Apps

| App | Composes |
|---|---|
| `server` | MCP transport + auth middleware + tool registry. No business logic. See [APP.md](src/db2st_mcp/apps/server/APP.md). |

## Shared

`src/db2st_mcp/shared/` — config loader, structured logger, error taxonomy, HTTP client wrapper. Imported by domains and apps. Never imports from them.

## Domain dependency graph

```
apps/server ──► domains/auth
apps/server ──► domains/tracking
domains/* ──► shared/
```

No domain imports another. No circular deps.

## Scaling model

Stateless pods behind Knative autoscaler. State lives in Redis (token store + quota counters). Concurrency-target autoscaling (default 50/pod). See [docs/KNATIVE.md](docs/KNATIVE.md).

## Tooling

- **uv** — deps + venv
- **ruff** — lint + format
- **mypy** — strict typing
- **pytest** + **pytest-asyncio** + **pytest-cov** — tests
- **pre-commit** — local enforcement
- **GitHub Actions** — CI (lint, type, unit, integration, e2e, security scan)

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md).

## Decision Log

**2026-05-15: Python over TypeScript.**
User preference. Python MCP SDK is mature, async ecosystem (httpx, asyncio) fits the I/O-bound workload, and packaging via uv is fast enough for Knative cold starts.

**2026-05-15: Clara philosophy.**
Codebase organized as apps/domains/shared with nested docs. Optimizes AI comprehension and human navigation. Tradeoff: more directories upfront vs. ad-hoc structure.

**2026-05-15: Streamable HTTP transport, stateless mode.**
Required for horizontal scale. Rules out stdio. Rules out server-affinity sessions (would pin clients to pods).

**2026-05-15: Knative Functions.**
Concurrency-based autoscaling + scale-to-zero match MCP's bursty traffic profile. Alternative (Cloud Run, Fargate) reconsidered if Knative adds operational drag.
