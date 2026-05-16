"""E2E: `MCP_ALLOWED_HOSTS` widens the MCP transport's allowlist at runtime.

Spawns `db2st-mcp serve` with:
- `DB2ST_AUTH_DISABLED=1` so we don't need a bearer.
- `MCP_ALLOWED_HOSTS=customhost.local` so the MCP transport's
  DNS-rebinding check accepts a non-standard `Host` header.

Then sends a real HTTP request with `Host: customhost.local`. The
transport's iter-17 unit test settles for "not 401, 421 acceptable"
because TestClient hard-codes `Host: testserver`. This e2e proves
the env-driven happy path actually works under uvicorn.
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
async def test_custom_host_accepted_when_in_allowlist() -> None:
    port = _free_port()
    env = os.environ.copy()
    env["TOKEN_STORE"] = "memory"
    env["LOG_LEVEL"] = "warning"
    env["DB2ST_AUTH_DISABLED"] = "1"
    env["MCP_ALLOWED_HOSTS"] = "customhost.local"

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
            # Force a non-default Host header. localhost would be accepted
            # by the SDK default; customhost.local proves *our* env var
            # extended the list.
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
                    "host": "customhost.local",
                },
            )

        # A 421 here would mean the transport rejected the Host; anything
        # else (200 success, or any 4xx/5xx from the MCP handler) means
        # the host check passed and the request reached tool dispatch.
        assert response.status_code != 421, (
            f"transport rejected Host=customhost.local — env var not honoured "
            f"(status={response.status_code}, body={response.text[:200]!r})"
        )
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()


@pytest.mark.asyncio
async def test_unlisted_host_still_rejected() -> None:
    """Negative control: a Host header NOT in the env's list still gets
    421 from the transport. Proves the allowlist isn't accidentally
    permissive.
    """
    port = _free_port()
    env = os.environ.copy()
    env["TOKEN_STORE"] = "memory"
    env["LOG_LEVEL"] = "warning"
    env["DB2ST_AUTH_DISABLED"] = "1"
    env["MCP_ALLOWED_HOSTS"] = "customhost.local"  # does NOT include 'somethingelse'

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
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                headers={
                    "content-type": "application/json",
                    "accept": "application/json, text/event-stream",
                    "host": "somethingelse.example.com",
                },
            )

        assert response.status_code == 421
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
