# DB2ST MCP

**Database-to-Structured-Tools MCP server.** A horizontally scalable Model Context Protocol server that exposes shipment tracking (and, by design, other data sources) as authenticated MCP tools. Built in Python, deployable as a Knative Function.

The first tool wraps DB Schenker's public shipment tracking endpoint. The shape of the codebase is built so additional carriers, databases, or third-party endpoints slot in behind the same transport, auth, and scaling primitives.

## Quickstart

```bash
uv sync --group dev              # install deps
cp .env.example .env             # configure
uv run db2st-mcp serve           # start HTTP server on :8080
uv run pytest                    # unit suite (integration tests deselected)
uv run pytest -m integration     # live upstream — needs unblocked egress IP
uv run pytest tests/e2e --report # E2E + Markdown report
```

## Use as a local Claude Code MCP

```bash
# from the repo root
uv sync --group dev --extra fallback   # extra installs Playwright
uv run playwright install chromium     # download the browser driver
claude mcp add db2st-mcp -s user \
  -e TOKEN_STORE=memory \
  -e DB2ST_HTML_FALLBACK=1 \
  -- uv --directory "$(pwd)" run db2st-mcp stdio

# verify
claude mcp list | grep db2st-mcp   # should show: ✓ Connected
```

`DB2ST_HTML_FALLBACK=1` enables the Playwright-based SPA scrape that
takes over when the upstream JSON path is rate-limited — which it
usually is from a fresh egress IP. Without the fallback, expect
`shipment not found` on most first-call attempts. The `[fallback]`
extra is what installs Playwright; see
[CONTRIBUTING.md](CONTRIBUTING.md#optional-extras-projectoptional-dependencies)
for the full list of optional extras.

Then ask Claude Code to track a shipment, e.g. `track DSV shipment 1806203236`.

Two MCP tools are registered:

| Tool | Returns |
|---|---|
| `track_shipment` | Full structured shipment (sender, receiver, package, history). |
| `track_shipment_events` | Just the chronological events timeline — lighter for poll-style clients. |

Want to see the raw JSON-RPC handshake + a `tools/call` exchange without
involving Claude Code? Run the example client:

```bash
uv run python scripts/example_call.py 1806203236
```

## Use as a deployed MCP (HTTP + auth)

```bash
# 1. start the server
uv run db2st-mcp serve

# 2. mint a token (one-time, secret is shown once)
uv run db2st-mcp mint --plan pro --limit 10000

# 3. call the MCP transport at /mcp with the bearer token.
#    Streamable HTTP requires the Accept header to list both types.

# 3a. Full shipment record:
curl https://your-host/mcp/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"track_shipment","arguments":{"reference":"1806203236"}}}'

# 3b. Events timeline only (lighter — for poll-style clients):
curl https://your-host/mcp/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"track_shipment_events","arguments":{"reference":"1806203236"}}}'
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system architecture and domain documentation.

## Testing

See [docs/TESTING.md](docs/TESTING.md) for the unit/integration/e2e split,
coverage gates, and CI workflows.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md).

## License

MIT
