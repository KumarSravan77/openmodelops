# Durable governance

The factory API persists workload specifications, gates, lifecycle history and optimistic versions through SQLAlchemy. Local tests use SQLite; the Compose deployment uses PostgreSQL. Concurrent updates require the expected version and stale writers fail with a conflict rather than silently overwriting an approval.

## Identity

`AUTH_MODE=oidc` requires a bearer token, validates it against issuer JWKS, checks issuer and audience, and derives subject, tenant and roles from signed claims. Request bodies cannot select their actor or tenant. Production must configure:

```text
AUTH_MODE=oidc
OIDC_ISSUER=https://identity.example
OIDC_AUDIENCE=openmodelops-factory
```

Development authentication is intentionally explicit and must not be used in a shared environment.

## Evidence signatures

Gate evidence contains a content digest and URI. In `FACTORY_ENV=production`, every gate submission must include an Ed25519 signature and trusted key identifier. `EVIDENCE_PUBLIC_KEYS_JSON` maps identifiers to base64-encoded raw public keys. Signatures cover the workload, gate, URI, digest and authenticated evaluator, preventing evidence from being moved between workloads or identities.

## Policy

Approval invokes a deterministic, versioned policy. The first policy version blocks unrestricted production egress, restricted-data egress and unreviewed extreme GPU availability targets. The response carries a policy digest so future audit records can identify the exact policy generation used for a decision.

The built-in policy is a portable baseline. A production platform can add OPA or Kyverno as an external evaluator, but external policy failure must fail closed for privileged transitions.
