# Product requirements: OpenModelOps AI SRE Factory

**Status:** Implementing  
**Product owner:** Platform Engineering  
**License:** MIT  
**Primary deployment:** Local containers, Kubernetes, then AWS  
**Product boundary:** Vendor-neutral control plane with optional provider integrations

## 1. Problem

ML, LLM, RAG and agent workloads are commonly built as isolated demonstrations. They lack a consistent path for identity, evidence, release approval, deployment, SLO ownership, incident response and retirement. Teams consequently duplicate controls and cannot prove that a model or agent passed the requirements associated with its production risk.

OpenModelOps provides one self-service factory contract and integrates specialized services without merging their implementation or weakening their security boundaries.

## 2. Users

| Persona | Primary need |
|---|---|
| ML engineer | Reproducible training, evaluation, registration and serving |
| AI/agent engineer | Governed prompts, models, tools, RAG and feedback |
| Platform engineer | Reusable golden paths and workload reconciliation |
| SRE/on-call engineer | SLOs, evidence, safe remediation and recovery validation |
| Security/risk reviewer | Identity, provenance, policy, approvals and auditability |
| FinOps owner | GPU, model, token and infrastructure cost accountability |

## 3. Product outcomes

1. Register a model, LLM, RAG or agent workload from one immutable specification.
2. Block production promotion until security, quality, reliability, observability, cost and rollback evidence passes.
3. Preserve separation between builders, evaluators, approvers and executors.
4. Connect existing services through versioned contracts and traceable events.
5. Detect SLO and security failures, investigate with evidence, recommend bounded remediation and verify recovery.
6. Run locally with open-source components while retaining optional AWS, Azure, GCP and commercial integrations.

## 4. Functional requirements

| ID | Requirement | Acceptance criterion | Status |
|---|---|---|---|
| FR-01 | Workload registration | API accepts validated model, LLM, RAG and agent specifications with immutable digests | Implemented |
| FR-02 | Readiness scorecard | Six required gates produce a deterministic blocking scorecard | Implemented |
| FR-03 | Separation of duties | Owner and gate evaluator cannot approve a release | Implemented |
| FR-04 | Lifecycle governance | Invalid approve, provision, release, suspend and retire transitions fail closed | Implemented |
| FR-05 | Component catalog | Registered services declare owner, domain, interface, health check, capabilities, maturity and evidence | Implemented |
| FR-06 | Interoperability events | Events include tenant, trace, schema, idempotency and CloudEvents-compatible envelope fields | Implemented |
| FR-07 | Durable control-plane state | Workload, gate and audit state survives process and node failure | Implemented PostgreSQL-compatible store; HA validation pending |
| FR-08 | Federated identity | Human and workload actors derive from OIDC/workload identity, never request bodies | Implemented OIDC enforcement; provider integration pending |
| FR-09 | Reconciliation | Factory controller reconciles approved specifications into Kubernetes resources | Planned |
| FR-10 | Evaluation integration | Evaluation engine signs results consumed by quality gates | Report adapter implemented; external signer deployment pending |
| FR-11 | Incident integration | ARIA evidence enters On-Call authority through signed, replay-resistant events | Typed adapters and existing signed ARIA→On-Call contract implemented; deployment pending |
| FR-12 | Automated rollback | Failed canary/SLO verification executes an approved deterministic rollback | Planned |

## 5. Non-functional requirements

| ID | Requirement | Initial target |
|---|---|---|
| NFR-01 | Factory API availability | 99.9% monthly |
| NFR-02 | Read latency | p95 under 300 ms excluding external providers |
| NFR-03 | Mutation latency | p95 under 1 s excluding asynchronous reconciliation |
| NFR-04 | Recovery | RPO 15 minutes; RTO 60 minutes |
| NFR-05 | Audit | Every privileged state transition records actor, reason, time and immutable target |
| NFR-06 | Tenant isolation | Identity, storage, retrieval and telemetry are tenant scoped |
| NFR-07 | Supply chain | Commit-addressed images, dependency scan, SBOM and signed provenance before production |
| NFR-08 | Privacy | Prompts, documents, secrets and personal data excluded from default telemetry |
| NFR-09 | Portability | Core path runs without a proprietary SaaS dependency |

## 6. Safety invariants

- Model output never directly mutates infrastructure.
- Every mutation maps to an allow-listed deterministic executor.
- Side-effecting actions include risk, target, rollback and recovery verification.
- Feedback is untrusted evidence until reviewed; it cannot directly retrain or promote.
- Changing an embedding model creates a separately validated vector index.
- Production promotion cannot bypass required gates.
- A failed dependency or policy service fails closed for privileged operations.

## 7. Out of scope for the first production release

- Training a foundation model from scratch.
- General-purpose autonomous shell access.
- Automatic acceptance of model-generated training labels.
- Universal support for every cloud and model provider.
- Claiming high availability without multi-node failure and restore evidence.

## 8. Success metrics

- 100% of production workloads registered with owner, SLO and immutable artifact.
- 100% of production releases carry all six gate results.
- 100% of privileged operations attributable to authenticated actors.
- At least 95% of incident hypotheses cite machine-verifiable evidence.
- At least 90% of known incident scenarios select the approved runbook.
- Zero automatic production remediations outside the allow-listed executor catalog.
- Restore, rollback and incident exercises executed at least quarterly.

## 9. Delivery milestones

1. **Control-plane contract:** workload API, lifecycle, gates, catalog and event envelope.
2. **Durable governance:** PostgreSQL, migrations, OIDC, policy engine and signed evidence.
3. **Service adapters:** ARIA, On-Call, model serving, agent gateway and evaluation engine.
4. **Kubernetes reconciliation:** controller, GitOps, progressive delivery and rollback.
5. **AI observability:** OpenTelemetry/OpenInference, Langfuse, Prometheus, Grafana and cost attribution.
6. **Resilience:** chaos scenarios, backup/restore and regional/cloud recovery exercises.

Each milestone requires automated tests, a runbook, threat-model changes, observable SLOs and reproducible demonstration evidence before it is marked verified.
