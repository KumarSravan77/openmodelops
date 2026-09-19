# Cross-repository integration contracts

OpenModelOps coordinates independently deployable components through typed adapters and durable events. It does not copy their internal implementations.

| Component | Factory interaction | Existing interface |
|---|---|---|
| ARIA | Health and evidence-based incident investigation | `GET /health`, `POST /investigate` |
| On-Call SRE | Authoritative incident retrieval and investigation | `GET /api/v1/incidents/{id}`, `POST .../investigate` |
| Model Serving | Serving readiness reconciliation | Admin `GET /readyz` |
| Production Agent Gateway | Governed, idempotent tool-call request | `POST /v1/tool-calls` |
| Evaluation Engine | Convert versioned JSON reports into signed quality evidence | CLI JSON report contract |

## Delivery guarantees

- Every mutating request carries an idempotency key.
- A durable SQL outbox separates factory transactions from network delivery.
- Transient failures use bounded exponential backoff.
- Five failed deliveries move the message to a dead-letter state.
- HTTP responses expose bounded error classes rather than remote response bodies.
- Trace and tenant fields travel in the factory event envelope.
- Component credentials are injected at runtime and never stored in catalog files.

## Trust boundaries

ARIA provides intelligence but cannot page or approve. On-Call owns incident state and remediation approval. Model Serving reports readiness but cannot promote its own artifact. Agent Gateway owns tool authorization and execution tickets. The Evaluation Engine produces evidence, but the factory independently verifies its signature and release policy.

## Remaining deployment work

The adapters, durable outbox and bounded dispatcher are implemented and tested. Production deployment still requires service discovery, workload identity, TLS/mTLS, trusted evidence-signing keys, network policies, secret-manager injection, scheduled worker deployment, dashboards and end-to-end failure testing against deployed component versions.
