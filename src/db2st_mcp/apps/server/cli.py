"""`db2st-mcp` console entrypoint.

Sprint 0: `serve` only. Sprint 2: `mint`, `tokens list`, `tokens revoke`.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import uvicorn

from db2st_mcp.shared.config import get_settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="db2st-mcp")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the HTTP server.")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 — container default
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    command = args.command or "serve"

    if command == "serve":
        settings = get_settings()
        uvicorn.run(
            "db2st_mcp.apps.server.main:app",
            host=args.host,
            port=args.port or settings.port,
            reload=args.reload,
            log_config=None,
        )
        return 0

    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
