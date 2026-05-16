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
└── /healthz              (pure liveness; returns `{"status": "ok"}`)
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

1. `configure_logging()` from `shared.logging` (module import time).
2. `build_deps(settings)` constructs the dependency bundle:
   `TokenStore` (memory vs upstash), `SchenkerClient`,
   `TrackingService`, and the response cache backend
   (memory `TTLCache` or `UpstashCache`, gated by
   `RESPONSE_CACHE_BACKEND`).
3. `build_mcp_server(deps.tracking_service)` instantiates `FastMCP`
   and registers the two domain tools.
4. `FastAPI(lifespan=...)` is constructed. The lifespan composes
   `mcp.session_manager.run()` so its task group is live before the
   first request hits `/mcp`.
5. `/healthz` route added.
6. Middleware added (LIFO order — last `add_middleware` runs first):
   - `bearer_auth_middleware` (skipped when `DB2ST_AUTH_DISABLED=1`)
   - `request_id_middleware` (added last → runs first; binds
     `request_id` to structlog contextvars before auth touches them)
7. `app.mount("/mcp", mcp.streamable_http_app())`.
8. `instrument_app(app)` opts the app into OpenTelemetry tracing
   when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; no-op otherwise.

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
