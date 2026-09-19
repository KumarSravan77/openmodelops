# OpenModelOps AI Platform

OpenModelOps is an MIT-licensed, vendor-neutral production reference designed to grow across four operational domains:

- **MLOps** — versioned datasets, reproducible training, registry, approval, rollout, drift monitoring and retraining.
- **LLMOps** — open-weight model catalog, evaluation, fine-tuning lineage, Ollama/vLLM serving and model routing.
- **AgentOps** — bounded tools, isolated memory, fail-closed guardrails, feedback, evaluation and controlled agent releases.
- **AIOps** — operational signals, anomaly correlation, incident assistance and approval-gated remediation.

No employer-specific names, systems, credentials or internal documentation are included.

## Architecture

```text
                        Git + CI quality gates
                                  |
                 +----------------+----------------+
                 |                                 |
       MLOps control plane                 Agent control plane
       datasets / runs / models            specs / prompts / tools
       evaluation / approvals              evaluations / releases
                 |                                 |
       model serving gateway  <---- approved endpoint contract
                 |                                 |
       batch + online inference             agent runtime workers
                 |                                 |
                 +---------- telemetry ------------+
                            OpenTelemetry
                    Prometheus / Grafana / logs
```

## Guarantees demonstrated

- Explicit lifecycle state machines prevent unreviewed promotion.
- Content-addressed artifacts and manifests support reproducibility and lineage.
- Separation of duties requires a different approver from the model trainer.
- Agent tools are deny-by-default, schema validated and constrained by policy.
- Guardrail unavailability fails closed for protected traffic.
- Raw prompts and credentials are excluded from default telemetry.
- Feedback becomes evaluation data; it never silently rewrites production behavior.
- Releases are immutable and support canary analysis and rollback.

## Quick start

```bash
python -m pytest -q
docker compose up --build
```

Then open:

- MLOps API: `http://localhost:8001/docs`
- Agent API: `http://localhost:8002/docs`
- MLflow: `http://localhost:5000`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

To start an open-weight model locally:

```bash
docker compose --profile local-models up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b
docker compose up --build agent-api
```

For an NVIDIA GPU environment, set `MODEL_PROVIDER=vllm`, point `MODEL_BASE_URL` at an approved vLLM server, and set `MODEL_ID` to its served model name. Both paths use the same governed `ModelEndpoint` contract.

## Repository map

```text
platforms/mlops/       lifecycle and promotion service
platforms/agents/      safe agent runtime and feedback service
packages/contracts/    shared, versioned API contracts only
infra/compose/         runnable local production-like stack
infra/kubernetes/      probes, policies, autoscaling and disruption controls
observability/         metrics and dashboards
evaluation/            golden datasets and quality gates
docs/                  architecture, security, SLOs and runbooks
```

See [production readiness](docs/PRODUCTION_READINESS.md) for the distinction between implemented controls and cloud deployment work that requires real infrastructure and credentials.
