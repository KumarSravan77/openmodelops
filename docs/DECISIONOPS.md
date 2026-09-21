# DecisionOps

DecisionOps is the vendor-neutral decision-intelligence boundary used by
OpenModelOps agents and operational workflows. It turns a model or rules-engine
response into a typed, validated and reproducible decision record. It does not
grant an agent permission to act; existing policy, approval and execution gates
remain authoritative.

## Implemented controls

- Typed `choice`, `score` and `probability` contracts.
- A versioned YAML question registry with immutable content digests.
- Required-state validation before a provider is called.
- Strict output validation, including option domains, score ranges and complete
  probability distributions.
- Provider abstraction with isolated failure handling, deterministic fallback
  and a resettable circuit breaker.
- Confidence thresholds that route uncertain decisions to human review.
- Critical-risk questions that cannot enable response caching.
- Reproducible records containing provider revision, question version and
  digest, policy version, state-schema version and canonical state digest.
- Bounded LRU caching whose key includes every version that can alter meaning.

The initial registry includes agent routing and remediation-support questions in
`catalog/questions/`. New questions must be reviewed like code and must define an
owner, required state, risk tier and confidence threshold.

An optional TypeSafe JEV adapter is implemented for controlled benchmarks and
shadow execution. See [JEV assessment](JEV_ASSESSMENT.md). It is not installed or
enabled by default.

## Trust boundary

DecisionOps separates four concerns:

```text
workflow state -> registered question -> decision provider -> validated record
                                                           |
                                                           v
                                           policy / approval / executor
```

A decision is evidence, not authorization. A result marked `accepted` may still
require RBAC, separation of duties, an immutable approval digest and an executor
allowlist. A result marked `fallback` records that the primary provider failed.
A low-confidence result is always marked `human_review`.

## Production provider requirements

No external proprietary decision service is embedded in this repository. A
production provider must be added through the `DecisionProvider` protocol and
must supply a stable provider ID and revision. Before it can influence a release
or remediation workflow, it must pass:

1. Schema, adversarial and malformed-output tests.
2. Golden-set calibration against domain experts.
3. Shadow-mode comparison with current decisions.
4. False-accept and false-reject thresholds by risk tier.
5. Failover, latency, capacity and circuit-breaker tests.
6. Audit, retention, privacy and access-control review.

The existing JudgeOps calibration and release-gate adapter can evaluate the
quality of a proposed provider, but JudgeOps must not judge its own promotion
without independent deterministic and human evidence.

## Current maturity

The contracts, registry, engine, validation, fallback, circuit breaker, cache
safety and audit records are implemented and unit tested. A production decision
provider-specific production qualification, durable decision-record service and
domain-specific calibration dataset are intentionally not claimed as complete.
