#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
docker build -t openmodelops-factory:local --build-arg SERVICE=factory "$ROOT"
docker build -t openmodelops-kubernetes-sre:local --build-arg SERVICE=kubernetes_sre --build-arg EXTRAS=kubernetes-sre "$ROOT"
kind load docker-image openmodelops-factory:local openmodelops-kubernetes-sre:local --name openmodelops
kubectl apply -f "$ROOT/deploy/kind/namespace.yaml"
kubectl -n openmodelops get secret platform-secrets >/dev/null 2>&1 || kubectl -n openmodelops create secret generic platform-secrets \
  --from-literal=factory-database-url='postgresql+psycopg://openmodelops:local-only@postgres:5432/openmodelops' \
  --from-literal=aria-integration-secret="$(openssl rand -hex 32)"
kubectl apply -k "$ROOT/deploy/kind"
kubectl -n openmodelops rollout status deployment/postgres --timeout=180s
kubectl -n openmodelops rollout status deployment/factory-api --timeout=180s
kubectl -n openmodelops rollout status deployment/kubernetes-sre-api --timeout=180s
"$ROOT/scripts/install-go-control-plane.sh"
