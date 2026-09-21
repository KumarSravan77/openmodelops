# ADR 0002: Go for the Kubernetes control plane

Status: accepted

## Decision

OpenModelOps uses Python for ML, LLM, RAG, evaluation and agent workflows. The
Kubernetes reconciliation, admission-policy and distributable CLI components
use Go. Rust is introduced only after a reproducible benchmark shows that a
gateway, streaming processor or data transformation cannot satisfy its latency,
throughput or memory-safety target in the existing implementation.

## Rationale

Python provides the strongest integration surface for PyTorch, Transformers,
MLflow, LangChain and evaluation frameworks. Go provides first-class Kubernetes
libraries, bounded resource use, straightforward concurrency and static binaries
for platform tooling. This boundary keeps model experimentation productive while
making infrastructure reconciliation deterministic and operationally small.

## Implemented components

- `omo`: local health diagnostics and Kind/workload operations.
- `openmodelops-operator`: reconciles `ModelDeployment`, `AgentDeployment` and
  `EvaluationRun` resources into Deployments, Services and Jobs.
- `openmodelops-admission`: fail-closed validation for immutable images,
  approval state, resource declarations, replica bounds and ports.

The operator runs with leader election, non-root containers, health probes and
least-privilege RBAC. The admission endpoint requires TLS 1.3 and limits request
size and processing time.

## Rust adoption gate

A Rust component requires a checked-in benchmark and an ADR demonstrating a
material improvement against an explicit SLO. Language diversity by itself is
not sufficient justification because every runtime adds patching, build,
observability and on-call cost.
