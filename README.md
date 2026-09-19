# OpenModelOps AI Platform

OpenModelOps is an MIT-licensed, vendor-neutral **AI SRE Factory** designed to operate four connected domains:

- **MLOps** — versioned datasets, reproducible training, registry, approval, rollout, drift monitoring and retraining.
- **LLMOps** — open-weight model catalog, evaluation, fine-tuning lineage, Ollama/vLLM serving and model routing.
- **AgentOps** — bounded tools, isolated memory, fail-closed guardrails, feedback, evaluation and controlled agent releases.
- **AIOps** — operational signals, anomaly correlation, incident assistance and approval-gated remediation.

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

The current implementation also includes an approval-gated AIOps control plane, OIDC/JWT verification and RBAC primitives, feature contracts, tenant-isolated Qdrant retrieval, and reproducible RayJob generation for distributed CPU/GPU training.

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
- AIOps API: `http://localhost:8003/docs`
- Factory API: `http://localhost:8004/docs`
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

Optional local infrastructure is isolated into Compose profiles:

```bash
docker compose --profile identity --profile retrieval \
  --profile feature-store --profile distributed-training up -d
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
packages/contracts/    shared, versioned API contracts only
packages/security/     OIDC verification and RBAC
feature_store/         Feast-compatible repository configuration
infra/compose/         runnable local production-like stack
infra/kubernetes/      probes, policies, autoscaling and disruption controls
observability/         metrics and dashboards
evaluation/            golden datasets and quality gates
docs/                  architecture, security, SLOs and runbooks
```

See [production readiness](docs/PRODUCTION_READINESS.md) for the distinction between implemented controls and cloud deployment work that requires real infrastructure and credentials.
See [AI SRE Factory](docs/AI_SRE_FACTORY.md) for the unified workload contract, release gates and delivery roadmap.
See the [product requirements](docs/PRODUCT_REQUIREMENTS.md) for personas, measurable requirements, acceptance criteria, safety invariants and delivery milestones.
See [durable governance](docs/DURABLE_GOVERNANCE.md) for persistence, OIDC, signed evidence and release-policy configuration.
