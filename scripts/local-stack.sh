#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ARIA_REPO=${ARIA_REPO:-"$(dirname "$ROOT")/aria-github-update"}
MODE=${2:-core}

ensure_network() {
  docker network inspect openmodelops-local >/dev/null 2>&1 || docker network create openmodelops-local >/dev/null
}

if [[ ${1:-} == down ]]; then
  docker compose -p openmodelops -f "$ROOT/docker-compose.yml" -f "$ROOT/deploy/local/compose.shared.yaml" --profile '*' down
  if [[ -f "$ARIA_REPO/docker-compose.yml" ]]; then
    docker compose -p aria -f "$ARIA_REPO/docker-compose.yml" -f "$ROOT/deploy/local/aria.compose.shared.yaml" --profile '*' down
  fi
  exit 0
fi

if [[ ${1:-} != up ]]; then
  echo "usage: $0 up {core|ai|full} | down" >&2
  exit 2
fi

ensure_network
if [[ -f "$ARIA_REPO/docker-compose.yml" ]]; then
  [[ -f "$ARIA_REPO/.env" ]] || bash "$ARIA_REPO/scripts/bootstrap-env.sh"
  ARIA_INTEGRATION_SECRET=${ARIA_INTEGRATION_SECRET:-$(sed -n 's/^ARIA_INTEGRATION_SECRET=//p' "$ARIA_REPO/.env" | head -1)}
  export ARIA_INTEGRATION_SECRET
fi
profiles=()
case "$MODE" in
  core) ;;
  ai) profiles=(--profile local-models --profile retrieval --profile telemetry);;
  full) profiles=(--profile local-models --profile retrieval --profile feature-store --profile identity --profile telemetry --profile ai-observability --profile kubernetes-sre);;
  *) echo "unknown mode: $MODE" >&2; exit 2;;
esac

docker compose -p openmodelops -f "$ROOT/docker-compose.yml" -f "$ROOT/deploy/local/compose.shared.yaml" "${profiles[@]}" up -d --build

if [[ -f "$ARIA_REPO/docker-compose.yml" ]]; then
  aria_profiles=()
  [[ "$MODE" != core ]] && aria_profiles=(--profile observability)
  docker compose -p aria -f "$ARIA_REPO/docker-compose.yml" -f "$ROOT/deploy/local/aria.compose.shared.yaml" "${aria_profiles[@]}" up -d --build
else
  echo "ARIA not found at $ARIA_REPO; OpenModelOps started without ARIA" >&2
fi

if [[ "$MODE" != core ]]; then
  "$ROOT/scripts/bootstrap-models.sh"
fi
