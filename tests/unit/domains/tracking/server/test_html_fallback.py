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
    _extract_package,
    _extract_party,
    _parse_event_text,
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


def test_to_shipment_maps_dom_provided_party_names() -> None:
    """DOM-selector hits for sender/receiver take precedence over body parsing."""
    data = {
        "senderName": "Acme",
        "receiverName": "Globex",
        "bodyText": "Shipment delivered. Stockholm to Berlin.",
        "events": [],
    }
    shipment = _to_shipment("1806203236", data)
    assert shipment.reference == "1806203236"
    assert shipment.sender.name == "Acme"
    assert shipment.receiver.name == "Globex"
    assert shipment.source == "html_fallback"
    # No date pattern in the body → no structured events extracted.
    assert shipment.history == []


def test_to_shipment_handles_empty_payload() -> None:
    shipment = _to_shipment("X", {})
    assert shipment.reference == "X"
    assert shipment.source == "html_fallback"
    assert shipment.history == []


def test_to_shipment_parses_structured_events_from_dom_rows() -> None:
    """Event rows captured from the DOM are parsed into TrackingEvents."""
    data = {
        "senderName": None,
        "receiverName": None,
        "bodyText": "",
        "events": [
            "2025/12/18 10:11 FR Dourges Delivered",
            "2025/12/18 07:20 FR Saint-Omer Out for Delivery",
            "2025/12/18 04:30 FR Saint-Omer Arrived",
            "2025/12/11 14:50 SE Sjuntorp Collected",
        ],
    }
    shipment = _to_shipment("1806290829", data)
    assert len(shipment.history) == 4
    # Newest first (deduped + sorted desc).
    assert shipment.history[0].status == "Delivered"
    assert shipment.history[0].at.year == 2025
    assert shipment.history[0].at.month == 12
    assert shipment.history[0].at.day == 18
    assert shipment.history[-1].status == "Collected"


def test_to_shipment_falls_back_to_bodyText_when_dom_events_empty() -> None:
    """When DOM selectors yield nothing, parse the body line-by-line."""
    body = "\n".join(
        [
            "Header text without date",
            "2025-12-18 10:11 Delivered at Dourges FR",
            "2025-12-11 14:50 Collected at Sjuntorp SE",
            "Footer with no date pattern",
        ]
    )
    data = {"bodyText": body, "events": [], "senderName": None, "receiverName": None}
    shipment = _to_shipment("X", data)
    assert len(shipment.history) == 2
    assert shipment.history[0].status == "Delivered"
    assert shipment.history[1].status == "Collected"


def test_to_shipment_dedupes_duplicate_events() -> None:
    data = {
        "events": [
            "2025/12/18 10:11 FR Delivered",
            "2025/12/18 10:11 FR Delivered",
        ],
        "bodyText": "",
        "senderName": None,
        "receiverName": None,
    }
    shipment = _to_shipment("X", data)
    assert len(shipment.history) == 1


def test_extract_package_pulls_weight_and_pieces() -> None:
    body = "Weight 800 kg\nNumber of packages 2"
    package = _extract_package(body)
    assert package.weight_kg is not None
    assert float(package.weight_kg) == 800.0
    assert package.piece_count == 2


def test_extract_package_converts_tonnes_to_kg() -> None:
    body = "Weight 1.5 t"
    package = _extract_package(body)
    assert package.weight_kg is not None
    assert float(package.weight_kg) == 1500.0


def test_extract_party_parses_address_line() -> None:
    section = "DSV Solutions AB\n46178, Sjuntorp, Sverige"
    party = _extract_party(section)
    assert party.name == "DSV Solutions AB"
    assert party.address.postal_code == "46178"
    assert party.address.city == "Sjuntorp"
    assert party.address.country == "Sverige"


def test_parse_event_text_skips_lines_without_date() -> None:
    assert _parse_event_text("just a header") is None
    assert _parse_event_text("Items per page 10") is None
    assert _parse_event_text("") is None


def test_parse_event_text_extracts_status_keyword() -> None:
    event = _parse_event_text("2025-12-18 10:11 FR Dourges Out for Delivery")
    assert event is not None
    assert event.status == "Out for delivery"


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
    fake_module.Error = type("Error", (Exception,), {})  # type: ignore[attr-defined]
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
async def test_fetch_raises_upstream_unavailable_when_extraction_yields_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty extraction = the SPA never rendered detail content.

    Treat as upstream-unavailable, not as an empty success — returning
    a blank Shipment to the caller masks the real failure mode and
    pollutes the cache with a permanent empty record.
    """
    _stub_playwright_returning(monkeypatch, {})

    fb = PlaywrightHtmlFallback()
    with pytest.raises(UpstreamUnavailableError):
        await fb.fetch("Z")


@pytest.mark.asyncio
async def test_fetch_raises_upstream_unavailable_when_only_landing_page_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the 1806290829 bug (2026-05-16).

    The headless Playwright context's resolver XHR was rate-limited by
    DSV (or never got an XSRF cookie), so the SPA never advanced past
    its landing/search state. The previous fallback treated absence of
    a not-found marker as success and returned a `Shipment` built from
    landing-page header text — empty fields plus one synthetic
    'scraped' event whose description was 'Welcome to DSV Tracking...'.

    The fix requires at least one DETAIL_MARKER in the scraped body.
    Landing-page text contains none, so this raises
    `UpstreamUnavailableError` and the breaker counts the failure
    instead of poisoning the cache.
    """
    landing_body = (
        "Welcome to\nDSV Tracking\nReference Number\nLooking for a specific reference?\nSearch"
    )
    _stub_playwright_returning(
        monkeypatch,
        {
            "bodyText": landing_body,
            "senderName": None,
            "receiverName": None,
            "events": [],
        },
    )
    fb = PlaywrightHtmlFallback()
    with pytest.raises(UpstreamUnavailableError, match="html fallback"):
        await fb.fetch("1806290829")


@pytest.mark.asyncio
async def test_fetch_returns_shipment_when_detail_markers_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive path: bodyText with at least one DETAIL_MARKER yields a Shipment."""
    detail_body = (
        "Your shipment has been delivered Delivered: 2025-12-18 10:11 "
        "From: 46178, Sjuntorp, Sverige Your shipment DWB Number 1806290829 "
        "Weight 800 kg Number of packages 2 STT-number VAN5022058 Product DSV LTL"
    )
    _stub_playwright_returning(
        monkeypatch,
        {
            "bodyText": detail_body,
            "senderName": "Sjuntorp",
            "receiverName": "Dourges",
            "events": [],
        },
    )
    fb = PlaywrightHtmlFallback()
    shipment = await fb.fetch("1806290829")
    assert shipment.reference == "1806290829"
    assert shipment.source == "html_fallback"
    assert shipment.sender.name == "Sjuntorp"
    assert shipment.receiver.name == "Dourges"


@pytest.mark.asyncio
async def test_fetch_accepts_headless_playwright_layout_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the 1806290829 false-positive (2026-05-16, second pass).

    The SPA renders a *different layout* under headless Chromium than
    under regular Chrome: a milestone-timeline view rather than the
    desktop detail card. The body text contains 'STT Number' (capital
    N, space) instead of 'STT-number' (lowercase, hyphen). The first
    pass of the fix only listed the Chrome variant in DETAIL_MARKERS
    and incorrectly raised UpstreamUnavailableError for the only ref
    still alive in DSV's tracking window. Both variants — plus the
    'Your shipment is delivered' phrase rendered in the headless
    milestone view — now appear in DETAIL_MARKERS. This test pins the
    actual body text captured from the live retest so future marker
    edits can't silently regress it.
    """
    # \xd7 is the multiplication sign the SPA renders as a close-button
    # glyph between milestones; kept as an escape so this file stays ASCII.
    headless_body = (
        "STT Number\nVAN5022058\nCollected\n2025/12/11 14:50\n\xd7\n"
        "Delivered\n2025/12/18 10:11\n\xd7\nHello!\n"
        "Your shipment is delivered!\nBooked"
    )
    _stub_playwright_returning(
        monkeypatch,
        {
            "bodyText": headless_body,
            "senderName": None,
            "receiverName": None,
            "events": [],
        },
    )
    fb = PlaywrightHtmlFallback()
    shipment = await fb.fetch("1806290829")
    assert shipment.reference == "1806290829"
    assert shipment.source == "html_fallback"


@pytest.mark.asyncio
async def test_fetch_maps_playwright_error_to_upstream_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real failure caught live this session: `Page.goto` timed out
    after 30s and the raw Playwright TimeoutError bubbled up to the
    MCP wire response. The fallback now catches everything that
    inherits from `playwright.async_api.Error` and maps to
    UpstreamUnavailableError so the response stays in the project's
    error taxonomy and the breaker counts the failure."""
    from db2st_mcp.shared.errors import UpstreamUnavailableError

    class _PlaywrightError(Exception):
        """Stand-in for `playwright.async_api.Error`."""

    class _Page:
        async def goto(self, *a: object, **kw: object) -> None:
            raise _PlaywrightError("Page.goto: Timeout 30000ms exceeded")

        async def evaluate(self, *a: object) -> dict[str, object]:
            return {}  # never reached

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
    fake_module.Error = _PlaywrightError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", fake_module)

    fb = PlaywrightHtmlFallback()
    with pytest.raises(UpstreamUnavailableError, match="html fallback failed"):
        await fb.fetch("X-REF")
