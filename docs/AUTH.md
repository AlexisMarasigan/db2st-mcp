# Auth & Quotas

> Cross-cutting reference. Domain detail in [domains/auth/DOMAIN.md](../src/db2st_mcp/domains/auth/DOMAIN.md).

## Token model

Opaque 32-byte random secret (base64url). Server stores only the SHA-256 hash:

```python
class TokenRecord(BaseModel):
    id: str                  # ULID
    hash: str                # sha256(secret)
    plan: Literal["free", "pro"]
    daily_limit: int
    created_at: datetime
    revoked_at: datetime | None
```

Raw secret shown once at mint time. Lookups hash the incoming header.

## Request flow

1. Client sends `Authorization: Bearer <secret>`.
2. Middleware hashes, looks up record. 401 if missing/revoked.
3. Middleware checks quota for current UTC day. 429 if exhausted.
4. Tool dispatcher runs handler.
5. On success, middleware atomically increments quota.

Quota incremented **post-success** so failed upstream calls don't burn budget.

## Quota storage

`TokenStore` protocol, two implementations:

- **InMemoryTokenStore** (`TOKEN_STORE=memory`) — dev only.
- **UpstashTokenStore** (`TOKEN_STORE=upstash`) — HTTP-based Redis. No persistent connection (survives serverless cold start).

Quota key: `quota:{token_id}:{YYYY-MM-DD}`. `INCR` returns new value; > limit → exhausted. 36h TTL.

## Lifecycle

- `uv run db2st-mcp mint --plan pro --limit 10000` — prints secret once, writes record.
- `uv run db2st-mcp tokens list`
- `uv run db2st-mcp tokens revoke <id>`

## Threat model (v1)

| Threat | Mitigation |
|---|---|
| Stolen token | Per-token quota caps blast radius; revoke + rotate. |
| Replay | Reads are idempotent; replay only burns quota. |
| Brute force | 32-byte secrets (~10^77 keyspace); rate-limited 401. |
| Header smuggling | Reject malformed `Authorization` early. |
| Error-message side channel | Generic 401 for "missing or invalid". |

## Out of scope (v1)

OAuth/OIDC, per-tool ACLs, audit-log retention policy.

## Decision Log

**2026-05-15: SHA-256, not bcrypt/argon2.**
Tokens are high-entropy random secrets, not human passwords. Hash exists only to prevent token-DB exfiltration. SHA-256 is fast enough for the auth hot path.

**2026-05-15: Upstash over self-hosted Redis.**
HTTP REST surface eliminates connection pool management in a scale-to-zero environment.
