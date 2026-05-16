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
3. Middleware atomically `INCR`s the day's quota counter. If the
   new count exceeds `daily_limit` → 429.
4. Tool dispatcher runs handler.

Quota is consumed **pre-handler**, so a failed upstream call still
burns one quota unit. Trade-off documented in the Decision Log
below; refund-on-failure is a future enhancement.

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
| Brute force | 32-byte secrets (2^256 keyspace ≈ 10^77). No per-IP 401 rate limit today — the keyspace alone makes guessing infeasible; an IP-level rate limit is reasonable defense-in-depth and tracked as a future hardening item. |
| Header smuggling | Reject malformed `Authorization` early. |
| Error-message side channel | Every auth-failure branch (missing header, wrong token, revoked token) returns the same `error: "unauthorized"` and the identical `message: "missing or invalid bearer token"`. Pinned by `test_auth_failure_message_is_identical_for_missing_and_invalid`. |

## Out of scope (v1)

OAuth/OIDC, per-tool ACLs, audit-log retention policy.

## Decision Log

**2026-05-15: SHA-256, not bcrypt/argon2.**
Tokens are high-entropy random secrets, not human passwords. Hash exists only to prevent token-DB exfiltration. SHA-256 is fast enough for the auth hot path.

**2026-05-15: Upstash over self-hosted Redis.**
HTTP REST surface eliminates connection pool management in a scale-to-zero environment.

**2026-05-16: Quota consumed pre-handler, not post-success.**
Atomic Redis `INCR` is the only race-free quota check we can do in
one round-trip. Decrement-on-success would need either a multi-step
compare-and-set (slower, more failure modes) or a refund step
that survives a crashed pod. Both are more complexity than today's
upstream cost justifies. Documented here because earlier versions
of this doc claimed the opposite — see middleware.py for the actual
behaviour.
