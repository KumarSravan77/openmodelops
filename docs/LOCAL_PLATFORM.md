# Shared local platform

The shared local platform is the primary supported deployment milestone. Cloud deployment profiles are intentionally outside this milestone.

## Profiles

| Profile | Purpose |
|---|---|
| `core` | APIs, MLflow, PostgreSQL, Prometheus and Grafana |
| `ai` | Core plus Ollama, Qdrant and OpenTelemetry |
| `full` | AI plus identity, Phoenix and the Kubernetes SRE API |
| `kind` | Kubernetes-native factory and bounded SRE runtime |

ARIA and OpenModelOps remain independently buildable repositories. The local launcher creates the external `openmodelops-local` network and attaches both Compose projects, giving the two APIs stable service aliases without merging or duplicating their datastores.

The shared overlay publishes the ARIA API on host port `8088` and its sample
checkout service on host port `9100` to avoid common local port collisions;
their container ports remain `8080` and `9000`.

## Start and validate

```bash
make local-up-ai
make local-smoke
```

The AI profile idempotently provisions `qwen2.5:3b` and `nomic-embed-text`. Set `MODEL_ID` or `EMBEDDING_MODEL` to override them.

Networks that require a private Python package mirror can pass `PIP_INDEX_URL` to the container build. If the mirror uses an internal certificate authority, install that CA in Docker rather than disabling TLS verification; `PIP_TRUSTED_HOST` exists only as an explicit local troubleshooting override.

For Kind:

```bash
make kind-create
make kind-deploy
make kind-smoke
```

## Security model

- Integration secrets are generated at deployment time and are not committed.
- Kubernetes inspection and execution use separate service accounts.
- The reader cannot patch workloads.
- The executor is namespace-scoped and cannot read Secrets.
- Live Kubernetes changes remain disabled until a separately authenticated approval path selects the executor identity.
- AI telemetry does not capture prompt content unless explicitly enabled.

## Acceptance boundary

The smoke tests verify service readiness, metrics exposure, and Kubernetes RBAC. A release is not locally ready when Compose rendering, Kustomize rendering, unit tests, or either smoke test fails.
