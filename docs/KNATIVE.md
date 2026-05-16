# Knative Deployment

## Why Knative Functions

- Scale to zero
- Concurrency-based autoscaling (matches MCP's bursty traffic)
- Plain HTTP (no special runtime)
- `func` CLI generates Dockerfile + buildpack + deploy in one step

## Function shape

Single HTTP handler, ASGI app exposed by `src/db2st_mcp/apps/server/main.py`. Listens on `$PORT`.

```
deploy/func.yaml      Knative Function manifest
deploy/Dockerfile     Multi-stage build (fallback when buildpacks unavailable)
```

## `func.yaml` essentials

```yaml
specVersion: 0.36.0
name: db2st-mcp
runtime: python
invocation: { format: http }
build: { builder: pack }
deploy:
  namespace: db2st
  annotations:
    autoscaling.knative.dev/metric: concurrency
    autoscaling.knative.dev/target: "50"
    autoscaling.knative.dev/minScale: "0"
    autoscaling.knative.dev/maxScale: "20"
envs:
  - { name: LOG_LEVEL, value: info }
  - { name: TOKEN_STORE, value: upstash }
  - { name: UPSTASH_REDIS_REST_URL,   value: "{{ secret:upstash-creds:url }}" }
  - { name: UPSTASH_REDIS_REST_TOKEN, value: "{{ secret:upstash-creds:token }}" }
  # Shared response cache so a hit from one pod is visible to all of them.
  - { name: RESPONSE_CACHE_BACKEND, value: upstash }
  - { name: RESPONSE_CACHE_TTL_SECONDS, value: "60" }
  # Production hostname(s) — required, otherwise the MCP transport rejects
  # external Host headers with HTTP 421. Comma-separated.
  - { name: MCP_ALLOWED_HOSTS, value: "mcp.example.com" }
```

## Autoscaling notes

- **Concurrency target 50** — tool calls are I/O-bound on Schenker. This
  is a *reasoned default*, not the result of a load test: real tuning
  is deferred until a cluster host runs `scripts/loadtest.k6.js`
  against a deployed revision (see `docs/ROADMAP.md` Sprint 3).
- **min=0** — scale to zero for cost. Python cold start target: <2s
  (unverified; needs cluster execution to measure).
- **max=20** — safety ceiling. Raising it means investigating abuse first.

## Local dev cluster

`scripts/local-cluster.sh` wraps the full bootstrap:

```bash
./scripts/local-cluster.sh
```

It creates the `kind` cluster (idempotent), applies the Knative operator
manifest, applies our minimal Serving CR (`deploy/knative-serving.yaml`),
waits for the control plane to become Ready, and runs
`func deploy --build --push=false` so the locally built image is loaded
into the cluster without going through a registry.

Required tools (script exits 2 if missing): `kind`, `kubectl`, `func`.

## Cold start hygiene

- Multi-stage build, prune dev deps. Target <120MB image.
- Lazy module-level imports for Redis client.
- No `await` at import time.

## Rollout

1. `func deploy --push`
2. Tag-based canary: deploy revision with `--tag canary`, route 10%.
3. Watch p95, error rate, 429 rate for 10 min.
4. `kn service update db2st-mcp --traffic latest=100`.

## Decision Log

**2026-05-15: Concurrency-target autoscaling, not RPS.**
MCP tool calls vary widely in upstream latency. Concurrency tracks real saturation; RPS hides head-of-line blocking.

**2026-05-15: `kind` for local dev.**
Local Kubernetes is cheap insurance against "works on my laptop, breaks on Knative" — and lets us load-test autoscaler tuning without paying for a cluster.

**2026-05-16: Cluster execution + load-driven tuning deferred.**
The bootstrap script, Serving CR, k6 script, and autoscaler annotations
all ship in-tree. Actually running them against `kind` requires a host
with `kind`/`kubectl`/`func` installed; this dev box doesn't have those.
Capturing the gap here (and in `docs/ROADMAP.md`) so a future iteration
from a cluster-ready box can pick up the work without re-deriving what
landed vs. what's still TODO.
