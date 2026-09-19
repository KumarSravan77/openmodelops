# Architecture and design decisions

## Two planes, one contract

The MLOps platform and agent platform are separate security and failure domains. The only mandatory dependency is the immutable `ModelEndpoint`/`ModelRelease` contract. Agent services cannot register or promote models, and training workloads cannot modify prompts, tools or agent policy.

## Extensible operations domains

```text
OpenModelOps
├── MLOps    data, features, training, registry, deployment and drift
├── LLMOps   open-weight models, fine-tuning, evaluation and serving
├── AgentOps prompts, tools, memory, guardrails, traces and feedback
└── AIOps    events, anomalies, incidents and approval-gated remediation
```

Each domain owns its APIs and state. Shared packages contain versioned contracts, not provider-specific business logic.

## Open-weight model path

- Ollama is the local-development path and works well on laptops and small servers.
- vLLM is the production GPU-serving path and exposes an OpenAI-compatible endpoint.
- Model IDs, upstream licenses, checksums, quantization, evaluation results and serving configuration belong in the model registry.
- A model cannot enter an agent release until the MLOps/LLMOps lifecycle marks its immutable revision approved.
- Model license terms are reviewed independently of this repository's MIT license. MIT covers OpenModelOps code, not downloaded model weights.

## MLOps lifecycle

```text
created -> training -> evaluating -> candidate -> approved
                                               -> deploying -> canary -> production
evaluating/candidate -> rejected
deploying/canary/production -> rolled_back -> retired
```

Every transition records actor, reason and time. Quality policy is evaluated before candidate creation. The run owner cannot approve their own release. Persistent writes use optimistic concurrency to prevent two reviewers from unknowingly overwriting each other.

Production extensions map cleanly to MLflow for experiments and registry, object storage for artifacts, a workflow engine for training, and Kubernetes model serving. The domain state machine remains authoritative so provider-specific registries cannot bypass governance.

## Agent lifecycle

```text
agent specification
 -> offline evaluation
 -> safety evaluation
 -> approved immutable release
 -> canary
 -> production
 -> feedback/traces
 -> curated evaluation candidates
```

Feedback is evidence, not training truth. Negative feedback enters a curation queue and is later transformed into reviewed golden cases. No production prompt, policy or model is modified automatically.

## Safety model

- Protected releases cannot serve if guardrails are unavailable.
- Input and output are checked before exposure or persistence.
- Tools are registered explicitly; arbitrary shell and network tools do not exist.
- Side-effecting tools require caller authorization and per-call approval.
- Traces contain hashes by default, not raw prompts.
- Release and model revisions are attached to every trace.

## Domain examples

### Financial risk

The MLOps plane gates a credit-risk model on discrimination, calibration, fairness gap and data freshness. Risk review is a distinct approval role. The agent plane can explain approved model documentation but cannot approve, replace or directly modify a decision model.

### 2D/3D media

Dataset manifests reference content-addressed geometry, renders, annotations and transformation parameters. Training lineage includes renderer/toolchain versions. Evaluation covers geometric validity, visual similarity, memory consumption and device-specific latency.

### Streaming and advertising

Feature pipelines consume event streams with schemas, event-time windows, replayable offsets and late-data policies. Online and batch feature parity is tested. Drift and consumer lag can trigger investigation, but retraining still passes evaluation and approval gates.

### Property operations

Document and image models operate on listings, inspections and maintenance records with tenant-level authorization. An operations agent may create a draft work order, but final submission is a side effect requiring approval and audit evidence.
