"""E2E: spawn `db2st-mcp serve` as a real OS process and exercise it.

Sibling of `test_mcp_stdio.py`. Covers the second production deployment
path — uvicorn + Streamable HTTP transport — that the unit-level
`test_http_transport.py` only exercises via `TestClient`.

Verifies:
- `/healthz` reachable within a 15s budget.
- `/mcp/` without bearer returns 401 with our structured error envelope.
- The process shuts down cleanly on SIGTERM.

The unit-level test already covers the post-auth path; this test
intentionally focuses on the things only a real OS process reveals
(bind, lifespan composition, signal handling).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import sys

import httpx
import pytest

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    """Allocate an ephemeral free TCP port for this test run."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _wait_for_healthz(url: str, deadline: float) -> None:
    async with httpx.AsyncClient(timeout=2.0) as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.25)
    raise TimeoutError(f"server never became healthy at {url}")


@pytest.mark.asyncio
async def test_serve_boots_and_rejects_unauthenticated_mcp_call() -> None:
    port = _free_port()
    env = os.environ.copy()
    env["TOKEN_STORE"] = "memory"
    env["LOG_LEVEL"] = "warning"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "db2st_mcp",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        deadline = asyncio.get_event_loop().time() + 15.0
        await _wait_for_healthz(f"http://127.0.0.1:{port}/healthz", deadline)

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"http://127.0.0.1:{port}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "clientInfo": {"name": "e2e", "version": "0.0.1"},
                    },
                },
                headers={
                    "content-type": "application/json",
                    "accept": "application/json, text/event-stream",
                },
            )

        assert response.status_code == 401
        body = response.json()
        assert body["error"] == "unauthorized"
        assert "bearer" in body["message"].lower()
    finally:
        proc.send_signal(signal.SIGTERM)
        clean_exit = False
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
            clean_exit = True
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
        # The lifespan `finally` walks `AppDeps.aclose()` -> three
        # `aclose()` calls (iter 130/131). If any of them deadlock
        # the process won't exit within the 5s budget and we'll
        # fall through to SIGKILL; that's the regression signal.
        assert clean_exit, "process did not honor SIGTERM within 5s"
