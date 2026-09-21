#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CLUSTER=${KIND_CLUSTER_NAME:-openmodelops}
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

docker build -t openmodelops-operator:local --build-arg COMPONENT=operator -f "$ROOT/go/Dockerfile" "$ROOT/go"
docker build -t openmodelops-admission:local --build-arg COMPONENT=admission -f "$ROOT/go/Dockerfile" "$ROOT/go"
kind load docker-image openmodelops-operator:local openmodelops-admission:local --name "$CLUSTER"

kubectl apply -f "$ROOT/deploy/kind/namespace.yaml"
kubectl apply -f "$ROOT/deploy/go/crds.yaml"
kubectl wait --for=condition=Established --timeout=60s \
  crd/modeldeployments.platform.openmodelops.io \
  crd/agentdeployments.platform.openmodelops.io \
  crd/evaluationruns.platform.openmodelops.io

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout "$tmp_dir/tls.key" -out "$tmp_dir/tls.crt" \
  -subj '/CN=openmodelops-admission.openmodelops.svc' \
  -addext 'subjectAltName=DNS:openmodelops-admission.openmodelops.svc,DNS:openmodelops-admission.openmodelops.svc.cluster.local' \
  >/dev/null 2>&1
kubectl -n openmodelops create secret tls openmodelops-admission-tls \
  --cert="$tmp_dir/tls.crt" --key="$tmp_dir/tls.key" \
  --dry-run=client -o yaml | kubectl apply -f -

ca_bundle=$(base64 < "$tmp_dir/tls.crt" | tr -d '\n')
sed "s|__CA_BUNDLE__|$ca_bundle|" "$ROOT/deploy/go/admission.yaml.tmpl" > "$tmp_dir/admission.yaml"
kubectl apply -f "$ROOT/deploy/go/operator.yaml"
kubectl apply -f "$tmp_dir/admission.yaml"
kubectl -n openmodelops rollout restart deployment/openmodelops-operator deployment/openmodelops-admission
kubectl -n openmodelops rollout status deployment/openmodelops-operator --timeout=180s
kubectl -n openmodelops rollout status deployment/openmodelops-admission --timeout=180s
