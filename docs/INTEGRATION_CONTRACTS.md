# Cross-repository integration contracts

OpenModelOps coordinates independently deployable components through typed adapters and durable events. It does not copy their internal implementations.

| Component | Factory interaction | Existing interface |
|---|---|---|
| ARIA | Health, evidence-based investigation and signed intelligence publication | `GET /health`, `POST /investigate`, `POST /api/v1/intelligence/aria` |
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
- ARIA intelligence is HMAC-bound to timestamp, nonce and exact JSON bytes; accepted signal IDs and nonces are durably unique.

## Trust boundaries

ARIA provides incident intelligence and its own bounded remediation workflow, but cannot approve an OpenModelOps workload release. OpenModelOps stores signed ARIA evidence and independently applies factory policy. Model Serving reports readiness but cannot promote its own artifact. Agent Gateway owns tool authorization and execution tickets. The Evaluation Engine produces evidence, but the factory independently verifies its signature and release policy.

## ARIA → OpenModelOps local setup

Configure one generated secret in both processes without committing it:

```bash
export ARIA_INTEGRATION_SECRET="$(openssl rand -hex 32)"

# OpenModelOps factory
export FACTORY_DB_PASSWORD="$(openssl rand -hex 24)"
docker compose up --build factory-db factory-api

# ARIA process/environment
export ON_CALL_SRE_URL="http://localhost:8004"
export ON_CALL_SRE_INTEGRATION_SECRET="$ARIA_INTEGRATION_SECRET"
```

ARIA publishes to `/api/v1/intelligence/aria`. The factory verifies `X-ARIA-Timestamp`, `X-ARIA-Nonce` and `X-ARIA-Signature`, then commits the evidence and replay keys in the factory database. Production must replace the shared secret with secret-manager injection and authenticated workload networking.

## Remaining deployment work

The adapters, signed ARIA ingress, durable outbox and bounded dispatcher are implemented and tested. Production deployment still requires service discovery, workload identity, TLS/mTLS, network policies, secret-manager injection, scheduled worker deployment, dashboards and end-to-end failure testing against deployed component versions.
