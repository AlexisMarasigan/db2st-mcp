"""`db2st-mcp` console entrypoint.

Subcommands:
- `serve`               — start the FastAPI HTTP server (Streamable HTTP transport).
- `stdio`               — start an MCP server on stdio (for local Claude Code MCP).
- `mint --plan --limit` — mint a new bearer token (prints the secret once).
- `tokens list`         — list known tokens.
- `tokens revoke <id>`  — mark a token revoked.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

import uvicorn

from db2st_mcp.apps.server.dependencies import build_deps
from db2st_mcp.apps.server.mcp_app import build_mcp_server
from db2st_mcp.shared.config import get_settings
from db2st_mcp.shared.logging import configure_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="db2st-mcp")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the HTTP server.")
    # S104 (ruff) / B104 (bandit): both flag the literal "0.0.0.0".
    # Inside a container the process must bind it so Knative's `$PORT`
    # sidecar reaches the listener.
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104  # nosec B104
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")

    sub.add_parser("stdio", help="Run as an MCP stdio server (for local Claude Code).")

    mint = sub.add_parser("mint", help="Mint a new bearer token.")
    mint.add_argument("--plan", choices=["free", "pro"], default="free")
    mint.add_argument("--limit", type=int, default=100, help="Daily request limit.")

    tokens = sub.add_parser("tokens", help="Manage tokens.")
    tokens_sub = tokens.add_subparsers(dest="tokens_command")
    tokens_sub.add_parser("list", help="List tokens.")
    revoke = tokens_sub.add_parser("revoke", help="Revoke a token by id.")
    revoke.add_argument("token_id")

    return parser


def _cmd_serve(args: argparse.Namespace) -> int:
    settings = get_settings()
    uvicorn.run(
        "db2st_mcp.apps.server.main:app",
        host=args.host,
        port=args.port or settings.port,
        reload=args.reload,
        log_config=None,
    )
    return 0


def _cmd_stdio() -> int:
    # Stdio transport must keep stdout clean for JSON-RPC framing; logs go to stderr.
    configure_logging()
    settings = get_settings()
    deps = build_deps(settings)
    mcp = build_mcp_server(deps.tracking_service)

    async def _run() -> None:
        try:
            await mcp.run_stdio_async()
        finally:
            await deps.aclose()

    asyncio.run(_run())
    return 0


def _cmd_mint(args: argparse.Namespace) -> int:
    settings = get_settings()
    deps = build_deps(settings)

    async def _run() -> dict[str, object]:
        try:
            record, secret = await deps.token_store.mint(args.plan, args.limit)
            return {
                "id": record.id,
                "plan": record.plan,
                "daily_limit": record.daily_limit,
                "secret": secret,
                "warning": "store this secret now — it is not recoverable.",
            }
        finally:
            await deps.aclose()

    result = asyncio.run(_run())
    print(json.dumps(result, indent=2))
    return 0


def _cmd_tokens_list() -> int:
    settings = get_settings()
    deps = build_deps(settings)

    from db2st_mcp.domains.auth.shared import TokenRecord

    async def _run() -> list[TokenRecord]:
        try:
            return await deps.token_store.list()
        finally:
            await deps.aclose()

    records = asyncio.run(_run())
    print(
        json.dumps(
            [
                {
                    "id": r.id,
                    "plan": r.plan,
                    "daily_limit": r.daily_limit,
                    "created_at": r.created_at.isoformat(),
                    "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                }
                for r in records
            ],
            indent=2,
        )
    )
    return 0


def _cmd_tokens_revoke(args: argparse.Namespace) -> int:
    settings = get_settings()
    deps = build_deps(settings)

    async def _run() -> None:
        try:
            await deps.token_store.revoke(args.token_id)
        finally:
            await deps.aclose()

    asyncio.run(_run())
    print(json.dumps({"id": args.token_id, "status": "revoked"}))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    command = args.command or "serve"

    # argparse already restricts `command` to {serve, stdio, mint, tokens}
    # (or None → defaults to "serve" above), so no else branch is needed.
    if command == "serve":
        return _cmd_serve(args)
    if command == "stdio":
        return _cmd_stdio()
    if command == "mint":
        return _cmd_mint(args)
    # command == "tokens"
    if args.tokens_command == "list":
        return _cmd_tokens_list()
    if args.tokens_command == "revoke":
        return _cmd_tokens_revoke(args)
    print("tokens: missing subcommand (list|revoke)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
