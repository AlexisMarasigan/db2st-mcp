#!/usr/bin/env python3
"""Talk to a fresh `db2st-mcp stdio` subprocess and print the exchange.

Newcomer demo: shows the JSON-RPC handshake + a real `tools/call`. Useful
when evaluating the project or wiring it into a different MCP client.

Usage:
    uv run python scripts/example_call.py                       # default ref
    uv run python scripts/example_call.py 1806203236            # custom ref
    DB2ST_HTML_FALLBACK=1 uv run python scripts/example_call.py # enable fallback
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

DEFAULT_REF = "1806203236"


async def _send(
    proc: asyncio.subprocess.Process,
    payload: dict[str, object],
    timeout: float = 45.0,
) -> dict[str, object]:
    # The asserts are mypy narrowing helpers — stdin/stdout are
    # guaranteed non-None because the parent uses `stdin=PIPE, stdout=PIPE`.
    assert proc.stdin is not None  # nosec B101
    assert proc.stdout is not None  # nosec B101
    proc.stdin.write((json.dumps(payload) + "\n").encode())
    await proc.stdin.drain()
    line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
    return json.loads(line.decode())  # type: ignore[no-any-return]


async def _notify(proc: asyncio.subprocess.Process, method: str) -> None:
    assert proc.stdin is not None  # nosec B101 — stdin=PIPE guarantees it
    proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method}) + "\n").encode())
    await proc.stdin.drain()


async def run(reference: str) -> int:
    env = os.environ.copy()
    env.setdefault("TOKEN_STORE", "memory")
    env.setdefault("LOG_LEVEL", "error")

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "db2st_mcp.apps.server.cli",
        "stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        print("→ initialize")
        init = await _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "example-call", "version": "0.0.1"},
                },
            },
        )
        print(json.dumps(init, indent=2))

        await _notify(proc, "notifications/initialized")

        print("\n→ tools/list")
        listing = await _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        print(json.dumps(listing, indent=2))

        print(f"\n→ tools/call track_shipment(reference={reference!r})")
        call = await _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "track_shipment",
                    "arguments": {"reference": reference},
                },
            },
        )
        print(json.dumps(call, indent=2))

        print(f"\n→ tools/call track_shipment_events(reference={reference!r})")
        events_call = await _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "track_shipment_events",
                    "arguments": {"reference": reference},
                },
            },
        )
        print(json.dumps(events_call, indent=2))
        return 0
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except TimeoutError:
            proc.kill()


def main() -> int:
    ref = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REF
    return asyncio.run(run(ref))


if __name__ == "__main__":
    sys.exit(main())
