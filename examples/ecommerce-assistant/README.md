# OpenModelOps e-commerce assistant

This is a local-first reference workload demonstrating hybrid retrieval,
corrective agent flow, governed MCP-style tools, citations, evaluation,
observability and deployment on OpenModelOps.

It uses an entirely synthetic product catalog. External scraping and live web
search are disabled, so tests are reproducible and no third-party terms,
credentials or customer information are involved.

## Run

```bash
docker compose --profile ecommerce up -d --build ecommerce-api
open http://localhost:8010
```

Or run it directly:

```bash
PYTHON=.venv/bin/python make run-ecommerce
```

Example:

```bash
curl -X POST http://127.0.0.1:8010/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"Recommend noise-cancelling headphones under CAD 300"}'
```

## Implemented

- Validated synthetic catalog ingestion.
- Deterministic hashed dense representation plus lexical scoring.
- Bounded maximal-marginal-relevance result diversification.
- Corrective query rewrite with a maximum of two retrieval attempts.
- Price constraint extraction.
- Grounded answers with product and source citations.
- Explicit insufficient-evidence response.
- Deny-by-default product search and comparison tools.
- JSON-RPC MCP-style `tools/list` and `tools/call` endpoint.
- FastAPI backend and dependency-free browser chat interface.
- Deterministic grounded generation by default, with optional Ollama or
  OpenAI-compatible local model generation using the same evidence contract.
- Prometheus metrics and privacy-safe optional OpenTelemetry traces.
- Golden retrieval cases, unit/API tests, Docker and Kubernetes manifests.

The JSON-RPC endpoint demonstrates the MCP tool boundary but does not claim the
complete MCP transport/session conformance suite. Full MCP SDK conformance,
Qdrant-backed dense/sparse indexing and LangGraph runtime compilation are the
next profile, after this deterministic baseline passes.

To use local Qwen through Ollama:

```bash
ECOMMERCE_MODEL_PROVIDER=ollama ECOMMERCE_MODEL_ID=qwen2.5:3b \
docker compose --profile ecommerce --profile local-models up -d ecommerce-api ollama
```
