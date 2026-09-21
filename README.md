# OpenModelOps AI Platform

OpenModelOps is an MIT-licensed, vendor-neutral **AI SRE Factory** designed to operate four connected domains:

- **MLOps** — versioned datasets, reproducible training, registry, approval, rollout, drift monitoring and retraining.
- **LLMOps** — open-weight model catalog, evaluation, fine-tuning lineage, Ollama/vLLM serving and model routing.
- **AgentOps** — bounded tools, isolated memory, fail-closed guardrails, feedback, evaluation and controlled agent releases.
- **AIOps** — operational signals, anomaly correlation, incident assistance and approval-gated remediation.
- **ReviewOps** — complete PR review retrieval, fork-policy latching, opt-in security findings and human-approved suggestion handling.

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

The current implementation also includes an approval-gated AIOps control plane, a read-only Kubernetes SRE diagnostic runtime, OIDC/JWT verification and RBAC primitives, feature contracts, tenant-isolated Qdrant retrieval, and reproducible RayJob generation for distributed CPU/GPU training.

The observability and evaluation layer now adds privacy-safe OpenTelemetry/OpenInference-style spans, OTLP adapters for Langfuse and Phoenix, an Opik integration boundary, provisioned Prometheus/Grafana assets, MLflow registry synchronization, Ragas/DeepEval release gates, and bounded LangChain/LangGraph RAG workflows.

JudgeOps adds governed LLM-as-a-judge execution with versioned rubrics, strict
structured results, ensemble disagreement policy, prompt-injection screening,
human calibration metrics and pairwise order-bias testing.

DecisionOps adds typed, versioned decision questions, provider isolation,
validated fallbacks, circuit breaking, confidence-based human review and
reproducible audit records. Decisions remain evidence; they never bypass policy,
approval or executor boundaries.

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
python3 -m pytest -q
make go-test
make local-up
make local-smoke
```

Python remains the ML and agent workflow language. Kubernetes reconciliation,
admission policy and the `omo` platform CLI are implemented in Go; see
[`docs/GO_CONTROL_PLANE.md`](docs/GO_CONTROL_PLANE.md). Rust adoption follows a
benchmark-first decision gate rather than adding another runtime without an
observed performance or memory-safety requirement.

The supported local milestone deliberately excludes AWS and Azure deployment profiles. `make local-up` starts the core services and the sibling ARIA checkout when it exists at `../aria-github-update`. Override that location with `ARIA_REPO=/absolute/path/to/aria`.

Use the resource-bounded profiles as needed:

```bash
make local-up-ai     # adds Ollama, Qdrant and OpenTelemetry; pulls Qwen + Nomic
make local-up-full   # adds identity, AI observability and Kubernetes SRE services
make local-down
```

Run the synthetic Canadian banking workload and its reproducible traffic gate:

```bash
make banking-up
make banking-smoke
LOAD_PROFILE=load make banking-load
```

The benchmark contains generated opaque account tokens and transactions only;
it has no association with a real financial institution or real customers.

Run the local-first synthetic e-commerce assistant:

```bash
docker compose --profile ecommerce up -d --build ecommerce-api
# browser UI and API documentation
open http://localhost:8010
open http://localhost:8010/docs
```

This reference workload demonstrates hybrid/MMR product retrieval, bounded
corrective search, grounded citations, deny-by-default MCP-style tools, a
FastAPI chat UI, golden evaluation cases and privacy-safe telemetry. It uses no
commerce-site scraping or customer data. See
[`examples/ecommerce-assistant/README.md`](examples/ecommerce-assistant/README.md).

Run the native Apple Silicon inference control plane in dependency-free
development mode:

```bash
PYTHON=.venv/bin/python make run-metal
curl http://127.0.0.1:8008/v1/runtime/profile
```

For real MLX inference on macOS, install `.[metal]`, set
`METAL_BACKEND=mlx` and select an MLX-compatible model. This service runs
natively because Linux containers cannot access Apple Metal. See
[`docs/METAL_RUNTIME.md`](docs/METAL_RUNTIME.md).

Then open:

- MLOps API: `http://localhost:8001/docs`
- Agent API: `http://localhost:8002/docs`
- AIOps API: `http://localhost:8003/docs`
- Factory API: `http://localhost:8004/docs`
- Review Agent API: `http://localhost:8005/docs`
- Kubernetes SRE API: `http://localhost:8006/docs` (profile: `kubernetes-sre`)
- JudgeOps API: `http://localhost:8009/docs`
- MLflow: `http://localhost:5000`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

To start an open-weight model locally:

```bash
docker compose --profile local-models up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b
docker compose up --build agent-api
```

### Local Kind environment

```bash
make kind-create
make kind-deploy
make kind-smoke
```

The Kind deployment creates isolated `openmodelops` and `openmodelops-managed`
namespaces, persistent PostgreSQL, runtime-generated integration secrets,
resource limits, health probes, default-deny ingress, and separate read-only and
change-executor service accounts. It also installs the Go operator, governed
workload CRDs, and fail-closed admission policy. Change execution remains
disabled by default.

For an NVIDIA GPU environment, set `MODEL_PROVIDER=vllm`, point `MODEL_BASE_URL` at an approved vLLM server, and set `MODEL_ID` to its served model name. Both paths use the same governed `ModelEndpoint` contract.

Optional local infrastructure is isolated into Compose profiles:

```bash
docker compose --profile identity --profile retrieval \
  --profile feature-store --profile distributed-training --profile telemetry up -d
```

The included Keycloak credentials are development defaults only. Set `KEYCLOAK_ADMIN_PASSWORD` before shared use. Production requires TLS, external secrets, database-backed identity, workload identity and least-privilege network policies.

## Implemented versus integration-ready

| Capability | Current level | Evidence |
|---|---|---|
| Model lifecycle and release governance | Implemented | `platforms/mlops/` |
| Guarded agent runtime and feedback queue | Implemented | `platforms/agents/` |
| Approval-gated incident remediation | Implemented | `platforms/aiops/` |
| OIDC verification and RBAC | Implemented library; Keycloak is an optional local profile | `packages/security/` |
| Feature validation | Implemented; Feast/Redis deployment is integration-ready | `platforms/features/`, `feature_store/` |
| Vector retrieval | Implemented Qdrant adapter with mandatory tenant filtering | `platforms/retrieval/` |
| Distributed training | Implemented immutable RayJob specification; requires KubeRay in Kubernetes | `platforms/training/` |
| Open-weight inference | Ollama and vLLM adapters implemented | `platforms/agents/providers.py` |
| AI workload factory and readiness scorecards | Implemented control-plane contract | `platforms/factory/` |
| OpenTelemetry, Prometheus and Grafana | Implemented; collector is an optional local profile | `packages/observability/`, `observability/` |
| Langfuse and Phoenix | Implemented via native OTLP export configuration | `packages/observability/` |
| Opik | Implemented native SDK adapter; external deployment required | `packages/observability/` |
| Ragas and DeepEval | Implemented optional runners and deterministic quality gate | `platforms/evaluation/` |
| Governed LLM-as-a-judge | Implemented versioned rubrics, strict parsing, ensembles, injection screening, calibration and release-gate adapter | `platforms/judgeops/` |
| Governed decision intelligence | Implemented typed contracts, question registry, validation, fallback, circuit breaker and reproducible decision records; production provider and durable service are pending | `platforms/decisionops/`, `catalog/questions/` |
| TypeSafe JEV | Optional Choice/Score/Noul adapter implemented for shadow evaluation; not installed or production-approved by default | `platforms/decisionops/jev.py`, `docs/JEV_ASSESSMENT.md` |
| LangChain and LangGraph | Implemented optional Runnable and bounded corrective graph | `platforms/rag/` |
| MLflow synchronization | Implemented registry, alias and governance-tag REST adapter | `platforms/integrations/mlflow.py` |
| Safety-gated PR review agent | Implemented review/comment retrieval, fork latch, security opt-in and approval gate | `platforms/reviewer/` |
| Kubernetes SRE diagnostics | Implemented official-client collection, deterministic parallel analysis, persistence and scheduled inspection | `platforms/kubernetes_sre/` |
| Kubernetes remediation | Implemented narrow scale/restart executor with immutable approval digest and three-party separation; deployment remains disabled until production identity and shared durable storage are configured | `platforms/kubernetes_sre/actions.py`, `infra/kubernetes/kubernetes-sre-executor-rbac.yaml` |
| ARIA incident evidence ingress | Implemented signed, time-bounded and replay-resistant durable ingestion | `platforms/integrations/aria_intelligence.py` |
| Go Kubernetes operator | Implemented model, agent and evaluation reconciliation with leader election and observed status | `go/cmd/operator/`, `go/internal/operator/` |
| Go admission policy | Implemented fail-closed TLS validation for approval, immutable images and resource bounds | `go/cmd/admission/`, `go/internal/admission/` |
| Go platform CLI | Implemented shared-platform diagnostics and Kind/workload operations | `go/cmd/omo/` |
| Synthetic banking performance workload | Implemented deterministic Canadian transaction generation, fraud scoring, k6 traffic profiles, SLO gates and dashboard | `platforms/banking/`, `performance/banking/` |
| E-commerce LLMOps reference workload | Implemented synthetic catalog, hybrid/MMR retrieval, corrective flow, citations, governed MCP-style tools, chat UI, tests and Kubernetes manifest | `platforms/ecommerce/`, `examples/ecommerce-assistant/` |
| Apple Silicon inference control plane | Implemented hardware profiling, memory admission, two-slot scheduling, prompt-cache indexing, MLX adapter, OpenAI-compatible API and metrics | `platforms/metal_runtime/` |

“Integration-ready” is deliberately not presented as a deployed production service: real production identity, storage, GPUs, DNS, TLS, backups and cloud policies must be supplied by the target environment.

## Repository map

```text
platforms/mlops/       lifecycle and promotion service
platforms/agents/      safe agent runtime and feedback service
platforms/aiops/       incident workflow and controlled remediation API
platforms/features/    feature contracts and validation
platforms/retrieval/   tenant-isolated vector retrieval
platforms/training/    reproducible Ray/Kubernetes training specs
platforms/factory/     self-service workload API and release scorecards
platforms/reviewer/    GitHub/GHES review aggregation and approval gate
platforms/kubernetes_sre/ Kubernetes inspection, specialist analysis and safety-gated changes
platforms/rag/         corrective RAG plus LangChain/LangGraph boundaries
platforms/evaluation/  Ragas/DeepEval runners and fail-closed quality gates
platforms/judgeops/    governed judges, rubrics, calibration and bias testing
platforms/decisionops/ typed decisions, question registry, failover and audit records
platforms/ecommerce/   product retrieval, corrective assistant and governed tools
packages/contracts/    shared, versioned API contracts only
packages/security/     OIDC verification and RBAC
packages/observability privacy-safe OpenTelemetry and provider configuration
feature_store/         Feast-compatible repository configuration
deploy/local/          shared ARIA/OpenModelOps Compose orchestration
deploy/kind/           reproducible local Kind control plane
infra/kubernetes/      probes, policies, autoscaling and disruption controls
observability/         metrics and dashboards
evaluation/            golden datasets and quality gates
docs/                  architecture, security, SLOs and runbooks
```

See [production readiness](docs/PRODUCTION_READINESS.md) for the distinction between implemented controls and cloud deployment work that requires real infrastructure and credentials.
See [AI SRE Factory](docs/AI_SRE_FACTORY.md) for the unified workload contract, release gates and delivery roadmap.
See the [product requirements](docs/PRODUCT_REQUIREMENTS.md) for personas, measurable requirements, acceptance criteria, safety invariants and delivery milestones.
See [durable governance](docs/DURABLE_GOVERNANCE.md) for persistence, OIDC, signed evidence and release-policy configuration.
See [integration contracts](docs/INTEGRATION_CONTRACTS.md) for ARIA, On-Call SRE, model-serving, agent-gateway and evaluation boundaries.
See [observability and evaluation](docs/OBSERVABILITY_AND_EVALUATION.md) for framework support levels, privacy controls and release-gate behavior.
See [JudgeOps](docs/JUDGEOPS.md) for judge trust boundaries, calibration gates and local-model configuration.
See [DecisionOps](docs/DECISIONOPS.md) for typed decisions, provider boundaries and production qualification requirements.
See the [JEV assessment](docs/JEV_ASSESSMENT.md) for the evidence, risks and shadow-mode adoption gate.
See the [JudgeOps dataset guide](docs/JUDGE_DATASET.md) for the 240-case candidate corpus and two-reviewer promotion workflow.
See [review agent](docs/REVIEW_AGENT.md) for PR review retrieval, fork latching, security checks and human approval rules.
See [Kubernetes SRE agent](docs/KUBERNETES_SRE_AGENT.md) for runtime boundaries, deployment and safety invariants.
