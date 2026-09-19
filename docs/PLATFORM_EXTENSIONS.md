# Production platform extensions

## Identity and access

`packages.security` validates signed OIDC tokens against issuer JWKS, checks issuer and audience, extracts tenant and realm/client roles, and fails closed when required roles are absent. Keycloak is provided for local integration testing. Production should use an organization-managed OIDC provider, TLS, short-lived tokens and workload identity.

## Feature platform

Feature contracts reject unknown, missing, mistyped, out-of-range and future-dated values before serving. The Feast repository demonstrates point-in-time offline data plus Redis online serving. The same validation must run at ingestion and inference to prevent training-serving skew.

## Distributed training

Training specifications require immutable image and dataset SHA-256 digests and reject plain-text secret variables. They compile into KubeRay `RayJob` resources with explicit CPU, memory and optional GPU requests. Production requires KubeRay, object storage, workload identity, quota, gang scheduling where appropriate, and artifact registration after quality gates.

## Vector retrieval

The Qdrant adapter requires a tenant for every search and injects it as a server-side payload filter. Production requires authenticated Qdrant, TLS, collection aliases for zero-downtime re-indexing, snapshots, restore tests and document-level authorization filters in addition to tenant isolation.

## AIOps safety model

The AIOps workflow moves through detection, correlation, investigation, recommendation, independent approval, execution and verification. Recommendation authors cannot approve their own actions. Side-effecting actions require risk and rollback metadata. Failed verification escalates rather than repeatedly mutating the system.

This is bounded automation, not unrestricted autonomy. Production executors should expose an allow-listed runbook catalog, scoped service accounts, concurrency limits, maintenance windows, circuit breakers and an immediate kill switch.
