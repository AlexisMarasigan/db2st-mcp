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
│   ├── request_id_middleware  ← apps/server/middleware.py
│   └── bearer_auth_middleware ← domains/auth/server/middleware.py
├── /mcp                  (Streamable HTTP transport)
│   └── tools:
│       ├── track_shipment        ← domains/tracking/server/tool.py
│       └── track_shipment_events ← domains/tracking/server/tool.py
└── /healthz              (liveness + token-store ping)
```

## Files

| File | Role |
|---|---|
| `main.py` | Builds the FastAPI app. Module-level `app` for ASGI servers. Mounts `/healthz` and the MCP transport. |
| `cli.py` | `db2st-mcp` console entrypoint. `serve`, `stdio`, `mint`, `tokens` subcommands. |
| `mcp_app.py` | Registers the MCP tools (`track_shipment`, `track_shipment_events`) against the FastMCP server. |
| `middleware.py` | `request_id_middleware` — generates / propagates `X-Request-ID` and binds it to structlog contextvars. |
| `dependencies.py` | DI wiring: token store, schenker client, tracking service, response cache backend. |

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
