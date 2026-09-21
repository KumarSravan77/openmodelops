#!/usr/bin/env bash
set -euo pipefail
MODEL_ID=${MODEL_ID:-qwen2.5:3b}
EMBEDDING_MODEL=${EMBEDDING_MODEL:-nomic-embed-text}
container=$(docker compose -p openmodelops ps -q ollama)
[[ -n "$container" ]] || { echo "Ollama is not running" >&2; exit 1; }
until docker exec "$container" ollama list >/dev/null 2>&1; do sleep 2; done
docker exec "$container" ollama pull "$MODEL_ID"
docker exec "$container" ollama pull "$EMBEDDING_MODEL"
docker exec "$container" ollama list
