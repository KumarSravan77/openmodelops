# Kubernetes SRE agent

This runtime provides a production-oriented foundation for autonomous Kubernetes diagnosis without granting an LLM or a general-purpose agent direct cluster mutation access.

## Implemented milestone

```text
Official Kubernetes API (read-only)
        |
zero-LLM scheduled snapshot
        |
parallel deterministic specialists
  workload / reliability / scaling
        |
stable findings + durable local history
        |
human-created proposal
        |
OIDC role checks + independent approval
        |
immutable proposal digest + expiry
        |
separate executor identity
        |
resource UID/version precondition
        |
allow-listed scale or restart
```

The scheduled path deliberately uses no generative model. This keeps routine health collection inexpensive, deterministic and testable. An LLM investigation layer can later summarize collected evidence, but it must remain behind the same read-only contracts and cannot execute arbitrary shell commands.

## Safety invariants

- The reader protocol contains no mutation methods.
- Execution is disabled by default.
- Only deployment scale and restart are allow-listed.
- The target namespace must be explicitly configured.
- Proposal author, approver and executor must be three different authenticated identities.
- Approval binds the complete proposal through a SHA-256 digest and expires after 15 minutes.
- Kubernetes UID and `resourceVersion` are checked immediately before mutation, preventing stale approval replay.
- Scale is bounded to 0–100 replicas and every action requires rollback instructions.
- The writer Role is namespace-scoped and cannot read Secrets, delete workloads or mutate cluster-scoped resources.
- Persistence failure aborts startup; there is no silent in-memory fallback.

## Run locally against a non-production cluster

Install the optional client and set an explicit kubeconfig:

```bash
python -m pip install -e '.[dev,kubernetes-sre]'
export KUBECONFIG=/absolute/path/to/a/test-kubeconfig
docker compose --profile kubernetes-sre up --build kubernetes-sre-api
```

The API is available on port 8006. Local execution remains off unless `KUBERNETES_SRE_EXECUTION_ENABLED=true` is explicitly set. Do not enable it against a shared cluster using development authentication.

## Kubernetes deployment

`infra/kubernetes/kubernetes-sre-reader.yaml` deploys only the diagnostic service with read-only RBAC. Replace the example image with an immutable digest and configure OIDC before applying it.

`infra/kubernetes/kubernetes-sre-executor-rbac.yaml` defines a separate, namespace-scoped executor identity. It is intentionally not attached to the reader Deployment. A production executor deployment must use a shared external database, export immutable audit events, enforce network policy and obtain short-lived workload identity before this binding is activated.

## Current boundary and next increment

This milestone is complete for deterministic collection, specialist analysis, persistence and the safety-gated scale/restart domain. It does **not** yet claim a fully autonomous production responder. Remaining production increments are:

1. PostgreSQL-backed shared proposal/report storage and append-only audit export.
2. A separately deployed executor service and queue.
3. Alert rules and SLO dashboards on top of the implemented OpenTelemetry spans and Prometheus inspection/finding/action metrics.
4. Evidence-aware investigation summaries and bounded LangGraph orchestration.
5. Post-action verification, automatic rollback, incident/ticket notifications and chaos/load qualification.

The architecture was informed by the MIT-licensed `langchain-samples/sre-agent` project, while this implementation uses original code and adds stricter identity, approval, stale-resource and RBAC controls.
