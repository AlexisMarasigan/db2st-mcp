"""Unit tests for `build_mcp_server`.

Exercises the registered `track_shipment` tool directly via FastMCP's
`call_tool` API so the tool body (`apps/server/mcp_app.py::_track_shipment`)
has actual unit coverage, instead of relying on the e2e subprocess
tests to indirectly hit those lines.
"""

from __future__ import annotations

from typing import Any

import pytest

from db2st_mcp.apps.server.mcp_app import build_mcp_server
from db2st_mcp.domains.tracking.shared.schemas import Shipment


class _StubService:
    """Stand-in matching the one method `_track_shipment` uses."""

    def __init__(self, shipment: Shipment) -> None:
        self._shipment = shipment
        self.calls: list[str] = []

    async def get_shipment(self, reference: str) -> Shipment:
        self.calls.append(reference)
        return self._shipment


@pytest.mark.asyncio
async def test_track_shipment_tool_returns_serialised_shipment() -> None:
    expected = Shipment(reference="1806203236", type="land_se")
    stub = _StubService(expected)
    mcp = build_mcp_server(stub)  # type: ignore[arg-type]

    result = await mcp.call_tool("track_shipment", arguments={"reference": "1806203236"})

    # FastMCP returns (content_blocks, structured_dict) for json_response.
    structured: Any
    if isinstance(result, tuple):
        _, structured = result
    else:
        structured = result

    assert stub.calls == ["1806203236"]
    assert isinstance(structured, dict)
    assert structured["reference"] == "1806203236"
    assert structured["type"] == "land_se"


@pytest.mark.asyncio
async def test_track_shipment_tool_propagates_validation_errors() -> None:
    """A reference too short to satisfy the Pydantic min_length=4
    constraint must surface via FastMCP rather than crash the server.
    """
    stub = _StubService(Shipment(reference="X", type="unknown"))
    mcp = build_mcp_server(stub)  # type: ignore[arg-type]

    # FastMCP wraps Pydantic ValidationError into a ToolError. Match on
    # the substring rather than the precise class so a future SDK rev
    # that reshuffles the hierarchy doesn't break this.
    with pytest.raises(Exception, match=r"(?i)reference|validation|short"):
        await mcp.call_tool("track_shipment", arguments={"reference": "a"})


@pytest.mark.asyncio
async def test_track_shipment_validation_error_is_clean_not_pydantic_raw() -> None:
    """Iter-170 caught raw Pydantic errors leaking the args-schema class
    name + Pydantic version + errors.pydantic.dev URL into the MCP wire
    response. The handler now catches ValidationError and re-raises as
    a clean InvalidInputError. Pins that the leaked tokens are gone."""
    stub = _StubService(Shipment(reference="X", type="unknown"))
    mcp = build_mcp_server(stub)  # type: ignore[arg-type]

    try:
        await mcp.call_tool("track_shipment", arguments={"reference": "a"})
    except Exception as e:
        msg = str(e)

    # None of these tokens should appear in the wire response.
    leaks = ("TrackShipmentArgs", "pydantic.dev", "type=string_too_short")
    for token in leaks:
        assert token not in msg, f"wire response leaked Pydantic internal: {token!r}"


@pytest.mark.asyncio
async def test_track_shipment_events_tool_returns_event_list() -> None:
    """The second registered tool returns just the timeline (sender /
    receiver / package omitted). Useful for poll-style clients.
    """
    from datetime import UTC, datetime

    from db2st_mcp.domains.tracking.shared.schemas import TrackingEvent

    events = [
        TrackingEvent(at=datetime(2026, 5, 15, 10, tzinfo=UTC), status="DELIVERED"),
    ]
    stub = _StubService(Shipment(reference="1806203236", type="land_se", history=events))
    mcp = build_mcp_server(stub)  # type: ignore[arg-type]

    result = await mcp.call_tool("track_shipment_events", arguments={"reference": "1806203236"})

    structured: Any
    if isinstance(result, tuple):
        _, structured = result
    else:
        structured = result

    # FastMCP wraps a list return into `{"result": [...]}`. Accept either
    # the raw list or the wrapped form.
    items = structured.get("result", structured) if isinstance(structured, dict) else structured
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["status"] == "DELIVERED"
