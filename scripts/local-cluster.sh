#!/usr/bin/env bash
# Spin up a local Knative cluster on `kind` and deploy db2st-mcp into it.
#
# Prereqs (will exit early if missing):
#   - kind     https://kind.sigs.k8s.io/
#   - kubectl  https://kubernetes.io/docs/tasks/tools/
#   - func     https://knative.dev/docs/getting-started/
#
# Idempotent: re-running re-applies the Knative manifests; the cluster
# stays up unless you `kind delete cluster --name db2st`.

set -euo pipefail

CLUSTER_NAME=${CLUSTER_NAME:-db2st}
KNATIVE_VERSION=${KNATIVE_VERSION:-v1.14.0}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required tool: $1" >&2
    exit 2
  }
}

require kind
require kubectl
require func

echo "==> kind cluster"
if ! kind get clusters | grep -qx "$CLUSTER_NAME"; then
  kind create cluster --name "$CLUSTER_NAME"
else
  echo "  cluster '$CLUSTER_NAME' already exists"
fi

echo "==> Knative operator ($KNATIVE_VERSION)"
kubectl apply -f "https://github.com/knative/operator/releases/download/knative-${KNATIVE_VERSION}/operator.yaml"

echo "==> Knative Serving"
kubectl apply -f "$HERE/deploy/knative-serving.yaml"

echo "==> wait for Serving control plane"
kubectl -n knative-serving wait --for=condition=Ready --timeout=300s knativeserving/knative-serving

echo "==> func deploy (build only — push=false for local cluster)"
cd "$HERE"
func deploy --build --push=false

echo
echo "done. Use 'kubectl get ksvc -n db2st' to find the route URL."
