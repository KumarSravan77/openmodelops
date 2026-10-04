# OpenModelOps Metal Runtime

The Metal Runtime is the Apple Silicon inference control plane for OpenModelOps.
It turns unified memory into an explicitly budgeted resource instead of waiting
for an inference process to fail or force macOS into heavy swap.

## Implemented

- Safe Apple hardware discovery without exposing serial numbers or identifiers.
- Model-weight and KV-cache memory estimation.
- Admission, context clamping, multimodal reserve and concurrency limits.
- Bounded scheduler with queue backpressure and deadlines. The development
  backend supports two workers; MLX is limited to one generation worker until
  safe native batching is demonstrated.
- Privacy-safe LRU prompt-cache metadata using SHA-256 keys.
- Lazy MLX-LM backend and a deterministic development backend.
- OpenAI-compatible model listing, non-streaming completions and SSE token streaming.
- Runtime planning/profile endpoints and Prometheus telemetry.
- Local benchmark harness for one or more client concurrency levels, including
  client-visible TTFT/TPOT, latency, throughput, errors and queue-wait time.
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

# Add `"stream":true` to the request body and use curl -N for token events.
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
| `METAL_MAXIMUM_SLOTS` | `1` for MLX, `2` for development | Concurrent generation workers; MLX rejects values other than 1 |
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

## Reproducible local benchmark

Start the native MLX server above using a model that fits your Mac. In another
terminal, run:

```bash
.venv/bin/python -m platforms.metal_runtime.benchmark \
  --stream --concurrency 1,2 --requests 4 --max-tokens 48 --require-real-model
```

The harness only connects to a loopback endpoint. It varies prompts, omits
prompt/response text from results, and refuses the development backend when
`--require-real-model` is used. Report the model and hardware with every run;
do not compare different models by throughput alone. This is a short smoke
benchmark, not a sustained capacity, answer-quality, or long-context test.

Measured 2026-10-03 on Apple M3 Pro, 36 GB unified memory, 18 GPU cores, with
`mlx-community/Qwen3-0.6B-4bit` and one MLX generation slot. Each level used
four short requests with up to 48 output tokens, after one warmup request:

| Client concurrency | Successes / errors | p50 / p95 latency | Aggregate output throughput | p95 queue wait |
|---:|---:|---:|---:|---:|
| 1 | 4 / 0 | 0.240 / 0.376 s | 112.3 tokens/s | 0.000 s |
| 2 | 4 / 0 | 0.541 / 0.660 s | 139.7 tokens/s | 0.228 s |

A separate streaming run on the same model and hardware measured the five
inference metrics in this format:

| Clients | p95 client TTFT | p95 client TPOT | p95 end-to-end latency | Output throughput | Errors |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.102 s | 0.0040 s/token | 0.288 s | 146.1 tokens/s | 0/4 |
| 2 | 0.359 s | 0.0040 s/token | 0.543 s | 164.8 tokens/s | 0/4 |

TTFT is measured from client request start to receipt of the first token
event. TPOT is the elapsed time between the first and last token events,
divided by the number of intervening token intervals. Backend-only timing is
also returned in `openmodelops` and exported as Prometheus histograms; it
excludes queue and network time. Runs with fewer than two generated tokens have
no TPOT value.

Cost per output token is **not measured by default**. The benchmark can model
it from explicitly supplied assumptions:

```bash
.venv/bin/python -m platforms.metal_runtime.benchmark --stream \
  --concurrency 1 --requests 4 --max-tokens 48 --require-real-model \
  --hardware-usd-per-hour 0.10 --average-watts 60 \
  --electricity-usd-per-kwh 0.15
```

Those example prices and power draw are hypothetical, not measured on this
Mac. The formula is `(wall_seconds / 3600) × (hardware_USD_per_hour +
average_watts / 1000 × electricity_USD_per_kWh) / generated_tokens`.
It excludes network, cooling, maintenance and idle-time allocation. Replace
the assumptions with observed power and your own cost model before using the
output for decisions.

The two-client throughput is an observed short-run aggregate, **not** proof of
parallel generation: requests queue behind a single MLX worker. These small
samples are not stable capacity estimates. The SHA-256 cache is metadata only, not
KV-cache reuse. Larger models, longer prompts, sustained loads, memory
pressure, quality and energy need separate qualification.

## Next runtime milestones

1. Native MLX batched generation instead of queued single-slot generation.
2. Backend-owned tensor prompt-cache integration and cache isolation tests.
3. Live memory-pressure and swap feedback for admission recalculation.
4. MLX-VLM image ingestion with resolution and vision-memory budgets.
5. Long-context, multimodal and multi-user qualification harness.
6. Signed benchmark manifests and Grafana runtime dashboards.
