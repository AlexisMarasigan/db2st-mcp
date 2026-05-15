"""auth-domain Pydantic models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

TokenPlan = Literal["free", "pro"]


class TokenRecord(BaseModel):
    """Persisted token record. The raw secret is never stored."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    hash: str  # sha256(secret), hex
    plan: TokenPlan
    daily_limit: int
    created_at: datetime
    revoked_at: datetime | None = None


class AuthContext(BaseModel):
    """What downstream code sees after the middleware accepts a request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token_id: str
    plan: TokenPlan
    remaining_today: int
