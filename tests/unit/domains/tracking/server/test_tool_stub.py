"""Sprint 0: prove the tool stub validates input and exposes a typed contract."""

from __future__ import annotations

import pytest

from db2st_mcp.domains.tracking.server.tool import (
    TrackShipmentArgs,
    track_shipment_tool,
)
from db2st_mcp.shared.errors import InvalidInputError


@pytest.mark.asyncio
async def test_empty_reference_raises_invalid_input() -> None:
    args = TrackShipmentArgs(reference="    ")
    with pytest.raises(InvalidInputError):
        await track_shipment_tool(args)


@pytest.mark.asyncio
async def test_stub_raises_not_implemented_until_sprint_1() -> None:
    args = TrackShipmentArgs(reference="1806203236")
    with pytest.raises(NotImplementedError):
        await track_shipment_tool(args)


def test_reference_min_length_enforced_by_pydantic() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrackShipmentArgs(reference="abc")
