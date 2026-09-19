# Production-readiness record

## Implemented and tested in this repository

- Model lifecycle state machine and quality gates
- Independent approval requirement
- Immutable artifact and endpoint contracts
- Optimistic concurrency for lifecycle writes
- Fail-closed guardrail behavior
- Deny-by-default tools and human approval for side effects
- Privacy-preserving trace records
- Feedback curation boundary
- Health/readiness endpoints and Prometheus metrics
- Non-root, read-only containers
- Kubernetes probes, HPA, PDB and network policy
- CI tests, linting, container builds and public-safety scanning

## Production integration points provided but requiring an environment

- Enterprise identity and RBAC at the API gateway
- PostgreSQL high availability and migrations
- Object storage and encryption-key policy
- MLflow authentication and external database/artifact store
- Workflow engine for distributed training
- GPU model serving and autoscaling
- OpenTelemetry collector, logs and alert routing
- Secret manager and workload identity
- Signed images, SBOM storage and admission policy
- Environment-specific Terraform and remote state
- Load, chaos, backup and recovery exercises

The repository must not be described as a deployed production service until those environment-dependent controls have been provisioned and verified with real evidence.
