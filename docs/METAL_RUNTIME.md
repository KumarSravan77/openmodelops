# OpenModelOps Metal Runtime

The Metal Runtime is the Apple Silicon inference control plane for OpenModelOps.
It turns unified memory into an explicitly budgeted resource instead of waiting
for an inference process to fail or force macOS into heavy swap.

## Implemented

- Safe Apple hardware discovery without exposing serial numbers or identifiers.
- Model-weight and KV-cache memory estimation.
- Admission, context clamping, multimodal reserve and concurrency limits.
- Bounded two-slot asynchronous scheduler with queue backpressure and deadlines.
- Privacy-safe LRU prompt-cache metadata using SHA-256 keys.
- Lazy MLX-LM backend and a deterministic development backend.
- OpenAI-compatible model listing and non-streaming chat completions.
- Runtime planning/profile endpoints and Prometheus telemetry.
- Unit, concurrency, API-contract and cache-isolation tests.

## Native setup

Linux Docker cannot access the Apple Metal GPU, so this runtime deliberately
runs on the macOS host.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev,metal]'
METAL_BACKEND=mlx \
METAL_MODEL_ID=mlx-community/Qwen3-8B-4bit \
METAL_MODEL_PARAMETERS_B=8 \
.venv/bin/python -m uvicorn platforms.metal_runtime.api:app \
  --host 127.0.0.1 --port 8008
```

Development mode does not download or load a model:

```bash
PYTHON=.venv/bin/python make run-metal
```

## API

```bash
curl http://127.0.0.1:8008/v1/runtime/profile

curl -X POST http://127.0.0.1:8008/v1/runtime/plan \
  -H 'Content-Type: application/json' \
  -d '{"prompt_tokens":64000,"max_tokens":4096,"active_slots":0}'

curl -X POST http://127.0.0.1:8008/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"mlx-community/Qwen3-8B-4bit",
    "messages":[{"role":"user","content":"Explain this architecture."}],
    "max_tokens":512
  }'
```

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `METAL_BACKEND` | `development` | `development` or `mlx` |
| `METAL_MODEL_ID` | `mlx-community/Qwen3-8B-4bit` | Local or Hugging Face MLX model |
| `METAL_MODEL_PARAMETERS_B` | `8` | Parameter count used by the planner |
| `METAL_MODEL_WEIGHT_BITS` | `4` | Weight precision used by the planner |
| `METAL_KV_BITS` | `8` | KV precision used by the planner |
| `METAL_KV_BYTES_PER_TOKEN_FP16` | `65536` | Architecture-specific FP16 KV cost |
| `METAL_SYSTEM_RESERVE_GB` | `6` | Memory protected for macOS and applications |
| `METAL_RUNTIME_RESERVE_GB` | `2` | Temporary activation/runtime reserve |
| `METAL_MAXIMUM_SLOTS` | `2` | Concurrent generation workers |
| `METAL_QUEUE_LIMIT` | `20` | Maximum waiting requests |

Memory estimates are admission safeguards, not measured capacity claims. A
model profile must be calibrated with observed resident memory, prefill peaks,
context-retrieval quality and repeated load tests before production use.

## Local validation evidence

Validated on 2026-09-21 using an Apple M3 Pro with 36 GB unified memory and an
18-core Metal 4 GPU:

| Check | Result |
|---|---|
| Hardware discovery | Correct chip, memory, CPU/GPU cores and Metal support |
| Development backend tests | Passed |
| Native MLX model | `mlx-community/Qwen3-0.6B-4bit` loaded successfully |
| OpenAI-compatible completion | Returned `Metal backend operational` |
| Token accounting | 27 prompt, 3 completion tokens from the tokenizer |
| Warm request wall time | 0.25 seconds |

The 0.6B checkpoint is an integration proof, not a 27B performance benchmark.
No 27B weights have been downloaded and no 27B throughput, context or quality
claim is made by this evidence.

## Next runtime milestones

1. Server-sent-event token streaming and disconnect cancellation.
2. Native MLX batched generation instead of independent worker invocations.
3. Backend-owned tensor prompt-cache integration and cache isolation tests.
4. Live memory-pressure and swap feedback for admission recalculation.
5. MLX-VLM image ingestion with resolution and vision-memory budgets.
6. Long-context, multimodal and multi-user qualification harness.
7. Signed benchmark manifests and Grafana runtime dashboards.
