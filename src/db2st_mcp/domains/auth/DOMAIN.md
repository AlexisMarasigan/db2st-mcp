# DOMAIN: auth

> Bearer tokens + per-token daily quotas. Stateless validation against a token store.

## Capability

- Validate `Authorization: Bearer <secret>` headers.
- Enforce per-token daily quotas (sliding day window, UTC).
- Mint / list / revoke tokens.

## Public surface

| Symbol | Where | What |
|---|---|---|
| `TokenRecord`, `TokenPlan`, `AuthContext` | `shared/schemas.py` | Persisted record + post-auth context. |
| `TokenStore` (Protocol), `RemainingQuota` | `shared/protocols.py` | Storage contract + return-type alias. |
| `InMemoryTokenStore` | `server/store.py` | In-memory dev store. |
| `UpstashTokenStore` | `server/upstash_store.py` | Upstash-Redis-backed prod store (optional `[redis]` extra). |
| `bearer_auth_middleware`, `authenticate` | `server/middleware.py` | Starlette/FastAPI middleware + the underlying coroutine. |

## Storage contract

```python
class TokenStore(Protocol):
    async def lookup(self, secret: str) -> TokenRecord | None: ...
    async def consume(self, token_id: str, day: date) -> RemainingQuota | Literal["exhausted"]: ...
    async def mint(self, plan: TokenPlan, daily_limit: int) -> tuple[TokenRecord, str]: ...
    async def revoke(self, token_id: str) -> None: ...
    async def list(self) -> list[TokenRecord]: ...
```

`lookup` hashes the incoming secret and returns the matching record.
`consume` atomically increments today's counter and returns remaining quota or
`"exhausted"`. `mint` returns `(record, raw_secret)` — raw secret is shown once.

## Quota semantics

- Window: rolling UTC day (`YYYY-MM-DD`).
- Key in Redis: `quota:{token_id}:{YYYY-MM-DD}` (TTL 36h).
- Incremented **post-success** so failed upstream calls are free.

## Dependencies on other domains

None.

## Failure modes

| Cause | Response |
|---|---|
| Missing `Authorization` | 401 `unauthorized` |
| Malformed header | 401 `unauthorized` |
| Hash not in store | 401 `unauthorized` |
| Token revoked | 401 `unauthorized` |
| Quota exhausted | 429 `quota_exceeded` (with retry-after) |

## Tests

- `tests/unit/domains/auth/server/` — store implementations, middleware
  (401, 429 quota-exhausted paths included).
- `tests/unit/apps/server/test_http_transport.py` — confirms the
  middleware is wired into the FastAPI app.

## Decision Log

**2026-05-16: Protocol + multiple implementations.**
`TokenStore` is a `typing.Protocol`. Allows in-memory dev, Upstash prod, and a future SQL backend without changing the middleware.

**2026-05-16: Quota counter atomic via INCR.**
Redis `INCR` is atomic and cheap; we read-after-write to decide exhaustion. Race-safe under concurrent requests on the same token.
