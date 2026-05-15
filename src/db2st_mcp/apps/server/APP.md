# APP: server

> 1,000 ft view of the server app. Composes domains; no business logic.

## Responsibilities

1. ASGI entry point.
2. Mount MCP Streamable HTTP transport at `/mcp`.
3. Auth middleware (delegates to `domains/auth`).
4. Tool registry: bind tool name → domain handler.
5. Health probe at `/healthz`.

## Composition

```
FastAPI app
├── middleware/
│   └── auth_middleware  ← domains/auth/server/middleware.py
├── /mcp                  (Streamable HTTP transport)
│   └── tools:
│       └── track_shipment ← domains/tracking/server/tool.py
└── /healthz              (liveness + token-store ping)
```

## Files

| File | Role |
|---|---|
| `main.py` | Builds the FastAPI app. Module-level `app` for ASGI servers. |
| `cli.py` | `db2st-mcp` console entrypoint. `serve`, `mint`, `tokens` subcommands. |
| `routes.py` | Health probe + introspection routes (not the MCP transport). |
| `dependencies.py` | DI wiring: token store, schenker client. |

## Boot order

1. `configure_logging()` from `shared.logging`.
2. Build `TokenStore` from `shared.config` (memory vs upstash).
3. Build `SchenkerClient` (lazy).
4. Register tools with the MCP server.
5. Mount transport + middleware on FastAPI.
6. Yield app to uvicorn.

## Failure surface

Errors from domain handlers (`Db2stError` subclasses) are translated to MCP
error payloads. Unknown exceptions become `internal`/500 with the message
redacted.

## Out of scope

- Sessions (stateless transport mode).
- Per-tool ACLs (sprint 5+).
- Admin UI.

## Decision Log

**2026-05-16: FastAPI under the MCP transport.**
The MCP Python SDK exposes a Starlette-compatible ASGI app for Streamable HTTP. Wrapping it in FastAPI gives us middleware + `/healthz` + OpenAPI for non-MCP endpoints, without re-implementing transport.
