"""DSV/Schenker public-tracking client.

Two-step resolver: search by ref → dispatch to type-specific detail
endpoint. Hides cookie/XSRF priming and header wrangling. Translates
upstream HTTP states into domain errors.

The fallback HTML-scrape path lives in `html_fallback.py` and is wired by
the orchestrator (`service.py`).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from db2st_mcp.domains.tracking.shared.schemas import ShipmentType
from db2st_mcp.shared.config import get_settings
from db2st_mcp.shared.drift import check as drift_check
from db2st_mcp.shared.errors import (
    NotFoundError,
    UpstreamUnavailableError,
)

_log = structlog.get_logger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

SPA_URL = "https://mydsv.dsv.com/app/tracking-public/"

# Maps `ShipmentType` to the detail-endpoint suffix used by the public API.
DETAIL_PATHS: dict[ShipmentType, str] = {
    "land": "/shipment/land/",
    "land_se": "/shipments/land/se/",
    "land_au": "/shipment/au/",
    "ocean": "/shipment/ocean/",
    "air": "/shipment/air/",
    "dsv": "/shipments/dsv/",
    "atol": "/shipments/atol/",
    "cos": "/shipments/cos/",
    "unknown": "/shipment/land/",  # safest default
}


class SchenkerClient:
    """Resolves a tracking reference to a structured upstream payload.

    The client is stateful only on the httpx client + a cached XSRF token.
    A single instance is safe to share across requests; it manages its own
    semaphore to keep per-instance concurrency under upstream's tolerance.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        max_concurrency: int = 8,
    ) -> None:
        settings = get_settings()
        timeout_s = settings.schenker_timeout_ms / 1000.0
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(settings.schenker_base_url).rstrip("/"),
            timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 3.0)),
            headers={
                "user-agent": UA,
                "accept": "application/json, text/plain, */*",
                "accept-language": "en-US,en;q=0.9",
                "x-version": "4",
                "referer": SPA_URL,
            },
            follow_redirects=True,
        )
        self._xsrf: str | None = None
        self._xsrf_lock = asyncio.Lock()
        self._sem = asyncio.Semaphore(max_concurrency)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> SchenkerClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # --- public API ----------------------------------------------------------

    async def resolve(self, reference: str) -> tuple[ShipmentType, str]:
        """Search by ref. Returns the preferred (type, upstream_id).

        Raises:
            NotFoundError: ref unknown to upstream.
            UpstreamUnavailableError: timeout, 5xx, or persistent 429.
        """
        from db2st_mcp.domains.tracking.server.parser import parse_resolver

        payload = await self._get_json(
            "/nges-portal/api/public/tracking-public/shipments",
            params={"query": reference},
        )
        drift_check("resolver", payload)
        candidates = parse_resolver(payload)
        if not candidates:
            raise NotFoundError(f"no shipments for reference {reference}")
        return candidates[0]

    async def fetch_detail(
        self,
        type_hint: ShipmentType,
        upstream_id: str,
    ) -> dict[str, Any]:
        """Fetch the type-specific detail payload."""
        suffix = DETAIL_PATHS.get(type_hint, DETAIL_PATHS["unknown"])
        payload = await self._get_json(
            f"/nges-portal/api/public/tracking-public{suffix}{upstream_id}"
        )
        # Endpoint key uses the ShipmentType so drift dashboards split
        # per shipment-mode -- a schema change in `land` shouldn't
        # silently obscure a separate change in `ocean`.
        drift_check(f"detail:{type_hint}", payload)
        if not isinstance(payload, dict):
            from db2st_mcp.shared.errors import ParseError

            raise ParseError(
                "expected object from detail endpoint",
                details={"got": type(payload).__name__},
            )
        return payload

    # --- internals -----------------------------------------------------------

    async def _prime_xsrf(self) -> None:
        async with self._xsrf_lock:
            if self._xsrf is not None:
                return
            try:
                await self._client.get(SPA_URL, headers={"accept": "text/html"})
            except httpx.HTTPError as e:
                raise UpstreamUnavailableError("failed to prime XSRF cookie") from e
            cookie = self._client.cookies.get("XSRF-TOKEN")
            if cookie:
                self._xsrf = cookie

    async def _get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> Any:
        await self._prime_xsrf()
        headers = {}
        if self._xsrf:
            headers["x-xsrf-token"] = self._xsrf

        async with self._sem:
            try:
                response = await self._client.get(path, params=params, headers=headers)
            except httpx.TimeoutException as e:
                raise UpstreamUnavailableError("upstream timeout", details={"path": path}) from e
            except httpx.HTTPError as e:
                raise UpstreamUnavailableError(
                    "upstream connection error", details={"path": path, "exc": type(e).__name__}
                ) from e

        if response.status_code == 404:
            raise NotFoundError("upstream returned 404", details={"path": path})
        if response.status_code == 429:
            raise UpstreamUnavailableError("upstream rate-limited (429)", details={"path": path})
        if response.status_code >= 500:
            raise UpstreamUnavailableError(
                f"upstream {response.status_code}",
                details={"path": path, "body_snippet": response.text[:200]},
            )
        if response.status_code >= 400:
            raise UpstreamUnavailableError(
                f"upstream {response.status_code}",
                details={"path": path, "body_snippet": response.text[:200]},
            )

        try:
            return response.json()
        except ValueError as e:
            raise UpstreamUnavailableError("upstream returned non-JSON") from e
