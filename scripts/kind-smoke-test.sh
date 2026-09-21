#!/usr/bin/env bash
set -euo pipefail
curl --fail --silent --retry 12 --retry-delay 2 http://localhost:8004/health/ready >/dev/null
curl --fail --silent --retry 12 --retry-delay 2 http://localhost:8006/health/ready >/dev/null
kubectl auth can-i get pods --as system:serviceaccount:openmodelops:sre-reader -n openmodelops-managed | grep -q yes
kubectl auth can-i patch deployments --as system:serviceaccount:openmodelops:sre-reader -n openmodelops-managed | grep -q no
kubectl auth can-i patch deployments --as system:serviceaccount:openmodelops:sre-executor -n openmodelops-managed | grep -q yes
echo 'Kind acceptance smoke test passed'
