"""Unit tests for the Playwright HTML fallback.

Avoids spawning a real browser by stubbing the playwright module symbol.
Exercises the import guard + the success-path mapping.
"""

from __future__ import annotations

import sys
import types

import pytest

from db2st_mcp.domains.tracking.server.html_fallback import (
    PlaywrightHtmlFallback,
    _to_shipment,
)
from db2st_mcp.shared.errors import UpstreamUnavailableError


@pytest.mark.asyncio
async def test_fetch_raises_when_playwright_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.async_api", None)

    fb = PlaywrightHtmlFallback()
    with pytest.raises(UpstreamUnavailableError):
        await fb.fetch("1806203236")


def test_to_shipment_maps_scraped_data() -> None:
    data = {
        "senderName": "Acme",
        "receiverName": "Globex",
        "bodyText": "Shipment delivered. Stockholm → Berlin.",
        "events": [],
    }
    shipment = _to_shipment("1806203236", data)
    assert shipment.reference == "1806203236"
    assert shipment.sender.name == "Acme"
    assert shipment.receiver.name == "Globex"
    assert shipment.source == "html_fallback"
    assert len(shipment.history) == 1
    assert shipment.history[0].status == "scraped"


def test_to_shipment_handles_empty_payload() -> None:
    shipment = _to_shipment("X", {})
    assert shipment.reference == "X"
    assert shipment.source == "html_fallback"
    assert shipment.history == []


def _stub_playwright_returning(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    """Install fake playwright modules that return the given payload from evaluate()."""

    class _Page:
        async def goto(self, *a: object, **kw: object) -> None: ...
        async def evaluate(self, *a: object) -> dict[str, object]:
            return payload

    class _Ctx:
        async def new_page(self) -> _Page:
            return _Page()

    class _Browser:
        async def new_context(self, **kw: object) -> _Ctx:
            return _Ctx()

        async def close(self) -> None: ...

    class _Chromium:
        async def launch(self, **kw: object) -> _Browser:
            return _Browser()

    class _PW:
        chromium = _Chromium()

        async def __aenter__(self) -> _PW:
            return self

        async def __aexit__(self, *a: object) -> None: ...

    fake_module = types.ModuleType("playwright.async_api")
    fake_module.async_playwright = _PW  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)


@pytest.mark.asyncio
async def test_fetch_raises_not_found_when_marker_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from db2st_mcp.shared.errors import NotFoundError

    _stub_playwright_returning(
        monkeypatch,
        {
            "bodyText": "Reference Number\nShipment not found!\nContact customer service",
            "senderName": None,
            "receiverName": None,
            "events": [],
        },
    )
    fb = PlaywrightHtmlFallback()
    with pytest.raises(NotFoundError):
        await fb.fetch("doesnotexist")


@pytest.mark.asyncio
async def test_fetch_returns_empty_shipment_when_extraction_yields_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stub out playwright so we can exercise the empty-data branch."""

    class _Page:
        async def goto(self, *a: object, **kw: object) -> None: ...
        async def evaluate(self, *a: object) -> dict[str, object]:
            return {}

    class _Ctx:
        async def new_page(self) -> _Page:
            return _Page()

    class _Browser:
        async def new_context(self, **kw: object) -> _Ctx:
            return _Ctx()

        async def close(self) -> None: ...

    class _Chromium:
        async def launch(self, **kw: object) -> _Browser:
            return _Browser()

    class _PW:
        chromium = _Chromium()

        async def __aenter__(self) -> _PW:
            return self

        async def __aexit__(self, *a: object) -> None: ...

    fake_module = types.ModuleType("playwright.async_api")
    fake_module.async_playwright = _PW  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)

    fb = PlaywrightHtmlFallback()
    shipment = await fb.fetch("Z")
    assert shipment.reference == "Z"
    assert shipment.source == "html_fallback"
