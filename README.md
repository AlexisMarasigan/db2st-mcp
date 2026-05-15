# DB2ST MCP

**Database-to-Structured-Tools MCP server.** A horizontally scalable Model Context Protocol server that exposes shipment tracking (and, by design, other data sources) as authenticated MCP tools. Built in Python, deployable as a Knative Function.

The first tool wraps DB Schenker's public shipment tracking endpoint. The shape of the codebase is built so additional carriers, databases, or third-party endpoints slot in behind the same transport, auth, and scaling primitives.

## Quickstart

```bash
uv sync                          # install deps
cp .env.example .env             # configure
uv run db2st-mcp                 # start dev server on :8080
uv run pytest                    # unit + integration tests
uv run pytest tests/e2e --report # E2E + Markdown report
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for system architecture and domain documentation.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md).

## License

MIT
