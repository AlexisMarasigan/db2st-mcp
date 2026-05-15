"""Storage contracts for the auth domain."""

from __future__ import annotations

from datetime import date
from typing import Literal, Protocol, runtime_checkable

from db2st_mcp.domains.auth.shared.schemas import TokenPlan, TokenRecord


class RemainingQuota(int):
    """Type alias to make intent explicit at call sites."""


@runtime_checkable
class TokenStore(Protocol):
    """Bearer-token storage + per-day quota counter."""

    async def lookup(self, secret: str) -> TokenRecord | None: ...

    async def consume(self, token_id: str, day: date) -> RemainingQuota | Literal["exhausted"]: ...

    async def mint(self, plan: TokenPlan, daily_limit: int) -> tuple[TokenRecord, str]: ...

    async def revoke(self, token_id: str) -> None: ...

    async def list(self) -> list[TokenRecord]: ...
