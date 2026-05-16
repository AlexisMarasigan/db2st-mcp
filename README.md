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

> Claude Code caches the MCP tool list per session. If you added this
> MCP before both tools were registered, restart Claude Code (or
> `claude mcp remove db2st-mcp -s user` and re-add) so the second
> tool is exposed. The same applies after pulling new code: the
> stdio subprocess holds whatever was on disk at `claude mcp add`
> time, so source changes (bug fixes, new tools) don't propagate
> until the next add.

Want to see the raw JSON-RPC handshake + a `tools/call` exchange without
involving Claude Code? Run the example client:

```bash
uv run python scripts/example_call.py 1806203236
```

## Use with other MCP clients

`db2st-mcp` is a vanilla stdio Model Context Protocol server, so any
MCP-compatible client can run it. The package is on PyPI, which means
the launch command across every client is the same:

```bash
uvx --from "db2st-mcp[fallback]" db2st-mcp stdio
```

This uses [`uv`](https://docs.astral.sh/uv/) to download the package
on first run, install the optional `[fallback]` extra (Playwright,
needed when the upstream JSON API is rate-limited), and start the
stdio transport. The first run will also need a one-time
`uvx playwright install chromium` to download the browser driver.

If you don't want `uv`, swap `uvx --from "db2st-mcp[fallback]"` for
`pipx run --spec "db2st-mcp[fallback]"` or any other tool runner.

The two environment variables the server respects are:

| Var | Effect |
|---|---|
| `TOKEN_STORE=memory` | Skip the bearer-token check (suitable for local stdio; HTTP deployments should use the default `upstash` store + minted tokens). |
| `DB2ST_HTML_FALLBACK=1` | Engage the Playwright SPA fallback when the upstream JSON API 429s. Strongly recommended for local use. |

### Claude Desktop

Edit the config file (create it if missing):

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "db2st-mcp": {
      "command": "uvx",
      "args": ["--from", "db2st-mcp[fallback]", "db2st-mcp", "stdio"],
      "env": {
        "TOKEN_STORE": "memory",
        "DB2ST_HTML_FALLBACK": "1"
      }
    }
  }
}
```

Restart Claude Desktop to pick up the change.

### Cursor

Per-project: `.cursor/mcp.json` in the repo root.
Global: `~/.cursor/mcp.json`.

Same JSON shape as Claude Desktop (the `mcpServers` object above).

### VS Code (GitHub Copilot Agent)

VS Code uses a different schema — `servers` (not `mcpServers`) and a
mandatory `type` field. Create `.vscode/mcp.json`:

```json
{
  "servers": {
    "db2st-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "db2st-mcp[fallback]", "db2st-mcp", "stdio"],
      "env": {
        "TOKEN_STORE": "memory",
        "DB2ST_HTML_FALLBACK": "1"
      }
    }
  }
}
```

### Continue (VS Code / JetBrains)

Create `.continue/mcpServers/db2st-mcp.yaml` in the workspace:

```yaml
mcpServers:
  - name: db2st-mcp
    type: stdio
    command: uvx
    args:
      - "--from"
      - "db2st-mcp[fallback]"
      - "db2st-mcp"
      - "stdio"
    env:
      TOKEN_STORE: memory
      DB2ST_HTML_FALLBACK: "1"
```

MCP tools are exposed in Agent mode only.

### Cline (VS Code extension)

Open the Cline panel → MCP Servers icon → **Configure MCP Servers**.
That opens `cline_mcp_settings.json` (under VS Code's global extension
storage). Add the same `mcpServers` block as Claude Desktop, plus
Cline-specific keys if you want auto-approval:

```json
{
  "mcpServers": {
    "db2st-mcp": {
      "command": "uvx",
      "args": ["--from", "db2st-mcp[fallback]", "db2st-mcp", "stdio"],
      "env": { "TOKEN_STORE": "memory", "DB2ST_HTML_FALLBACK": "1" },
      "disabled": false,
      "alwaysAllow": []
    }
  }
}
```

### Zed

Zed keys MCP servers under `context_servers` (not `mcpServers`).
Edit `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "db2st-mcp": {
      "command": {
        "path": "uvx",
        "args": ["--from", "db2st-mcp[fallback]", "db2st-mcp", "stdio"]
      },
      "env": {
        "TOKEN_STORE": "memory",
        "DB2ST_HTML_FALLBACK": "1"
      }
    }
  }
}
```

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json` (Windows:
`%USERPROFILE%\.codeium\windsurf\mcp_config.json`). Same JSON shape
as Claude Desktop.

### Remote / HTTP-only clients

If your client doesn't speak stdio, point it at the deployed HTTP
transport instead (see the next section for how to start one + mint
a token). Most clients accept the same `url` + `headers` shape:

```json
{
  "mcpServers": {
    "db2st-mcp": {
      "url": "https://your-host/mcp/",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

### Programmatic / custom clients

Any MCP SDK can drive `db2st-mcp` directly — there's nothing
Claude-specific about the wire protocol. The `tools/list` →
`tools/call` flow is plain JSON-RPC 2.0, and
[`scripts/example_call.py`](scripts/example_call.py) is a 50-line
reference implementation of a stdio client doing the handshake +
calling `track_shipment`. Adapt that pattern for any agent framework
(LangChain MCP adapter, LlamaIndex tools, your own runner) — the
SDK choice is the consumer's; the server side stays unchanged.

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
