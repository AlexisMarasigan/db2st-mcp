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
```

## Autoscaling notes

- **Concurrency target 50** — tool calls are I/O-bound on Schenker. Tune from real p95 in sprint 3.
- **min=0** — scale to zero for cost. Python cold start target: <2s.
- **max=20** — safety ceiling. Raising it means investigating abuse first.

## Local dev cluster

`kind` + Knative for end-to-end:

```bash
kind create cluster --name db2st
kubectl apply -f https://github.com/knative/operator/releases/download/knative-v1.14.0/operator.yaml
kubectl apply -f deploy/knative-serving.yaml
func deploy --build --push=false
```

`scripts/local-cluster.sh` wraps this in sprint 3.

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
