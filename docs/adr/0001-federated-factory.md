# ADR-0001: Federated factory instead of a monolith

## Status

Accepted

## Decision

OpenModelOps is the workload, governance and integration control plane. Existing focused repositories remain independently deployable components connected through versioned APIs and events. Their code is not copied into a single repository.

## Rationale

- Training, serving, agent execution and incident response have different failure and security domains.
- Independent services can scale, release and fail without taking down the entire platform.
- Portfolio claims remain attributable to executable repositories rather than architecture-only documents.
- A component can be replaced without changing the factory workload contract.

## Consequences

- Every component must publish a health contract, interface version, owner and evidence.
- Cross-service workflows require idempotency, trace propagation, authentication and replay protection.
- Integration tests and compatibility matrices become release requirements.
- The factory must not report a component as verified merely because it appears in the catalog.
