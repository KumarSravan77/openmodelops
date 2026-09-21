#!/usr/bin/env bash
set -euo pipefail

check() {
  name=$1 url=$2
  curl --fail --silent --show-error --retry 30 --retry-delay 2 \
    --retry-connrefused --retry-all-errors "$url" >/dev/null
  printf 'ok  %s\n' "$name"
}

check mlops http://localhost:8001/health/ready
check agents http://localhost:8002/health/ready
check aiops http://localhost:8003/health/live
check factory http://localhost:8004/health/ready
check reviewer http://localhost:8005/health/ready
check aria http://localhost:8088/health
check prometheus http://localhost:9090/-/ready
check grafana http://localhost:3000/api/health
curl --fail --silent http://localhost:8001/metrics | grep -q openmodelops
curl --fail --silent http://localhost:8002/metrics | grep -q openmodelops

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ARIA_REPO=${ARIA_REPO:-"$(dirname "$ROOT")/aria-github-update"}
integration_secret=$(sed -n 's/^ARIA_INTEGRATION_SECRET=//p' "$ARIA_REPO/.env" | head -1)
[[ -n "$integration_secret" ]] || { echo "ARIA integration secret is missing" >&2; exit 1; }
python3 - "$integration_secret" <<'PY'
import hashlib
import hmac
import json
import sys
import time
import urllib.request
import uuid

secret = sys.argv[1]
signal_id = f"local-smoke-{uuid.uuid4()}"
payload = {
    "schema_version": "1.0",
    "source": "aria",
    "signal_id": signal_id,
    "tenant": "local-smoke",
    "workload_id": "shared-compose",
    "severity": "low",
    "confidence": 1.0,
}
body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
timestamp = str(int(time.time()))
nonce = str(uuid.uuid4())
message = timestamp.encode() + b"." + nonce.encode() + b"." + body
signature = "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
request = urllib.request.Request(
    "http://localhost:8004/api/v1/intelligence/aria",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-ARIA-Timestamp": timestamp,
        "X-ARIA-Nonce": nonce,
        "X-ARIA-Signature": signature,
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=10) as response:
    result = json.load(response)
if response.status != 200 or result != {"signal_id": signal_id, "status": "accepted"}:
    raise SystemExit(f"signed ARIA integration failed: {result}")
print("ok  signed ARIA-to-OpenModelOps evidence")
PY
echo 'shared local acceptance smoke test passed'
