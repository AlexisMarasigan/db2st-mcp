"""Error taxonomy shared across domains.

Each error maps to a stable code in API responses. Domain code raises these;
the apps layer translates them to MCP / HTTP errors.
"""

from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "not_found",
    "upstream_unavailable",
    "parse_error",
    "invalid_input",
    "unauthorized",
    "quota_exceeded",
    "internal",
]


class Db2stError(Exception):
    """Base class for all domain errors."""

    code: ErrorCode = "internal"
    http_status: int = 500

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(Db2stError):
    code: ErrorCode = "not_found"
    http_status: int = 404


class UpstreamUnavailableError(Db2stError):
    code: ErrorCode = "upstream_unavailable"
    http_status: int = 502


class ParseError(Db2stError):
    code: ErrorCode = "parse_error"
    http_status: int = 502


class InvalidInputError(Db2stError):
    code: ErrorCode = "invalid_input"
    http_status: int = 400


class UnauthorizedError(Db2stError):
    code: ErrorCode = "unauthorized"
    http_status: int = 401


class QuotaExceededError(Db2stError):
    code: ErrorCode = "quota_exceeded"
    http_status: int = 429
