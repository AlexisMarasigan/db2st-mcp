"""Unit tests for the shared error taxonomy."""

from __future__ import annotations

import pytest

from db2st_mcp.shared.errors import (
    Db2stError,
    InvalidInputError,
    NotFoundError,
    QuotaExceededError,
    UnauthorizedError,
    UpstreamUnavailableError,
)


@pytest.mark.parametrize(
    ("exc_class", "code", "status"),
    [
        (NotFoundError, "not_found", 404),
        (UpstreamUnavailableError, "upstream_unavailable", 502),
        (InvalidInputError, "invalid_input", 400),
        (UnauthorizedError, "unauthorized", 401),
        (QuotaExceededError, "quota_exceeded", 429),
    ],
)
def test_error_codes_and_status_codes(
    exc_class: type[Db2stError],
    code: str,
    status: int,
) -> None:
    err = exc_class("boom", details={"k": "v"})
    assert err.code == code
    assert err.http_status == status
    assert err.message == "boom"
    assert err.details == {"k": "v"}


def test_base_error_defaults_to_internal() -> None:
    err = Db2stError("oops")
    assert err.code == "internal"
    assert err.http_status == 500
    assert err.details == {}
