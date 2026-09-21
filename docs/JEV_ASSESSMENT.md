# JEV adoption assessment

Assessment date: 2026-09-21.

## Decision

JEV is a good **proof-of-concept and shadow-provider candidate** for narrow,
high-volume typed decisions. It is not yet approved as an OpenModelOps production
dependency or an autonomous execution authority.

The optional `JevDecisionProvider` maps OpenModelOps Choice, Score and
Probability questions to TypeSafe Choice, Score and Noul primitives. It sits
behind the existing provider protocol, validation, circuit breaker, deterministic
fallback, confidence policy and human-review boundary. The SDK is not installed
by default and OpenModelOps continues to work without JEV.

## Evidence supporting a trial

- TypeSafe documents typed Choice, Score and Noul outputs, including complete
  Choice distributions and confidence, which fit the DecisionOps contract.
- Multiple questions sharing the same state can be evaluated independently in
  one request, a useful shape for agent trace and incident classification.
- The official Python SDK is publicly available under the MIT license.
- Published pricing is attractive for high-volume evaluation if the advertised
  quality and latency reproduce on our own traces.

Sources: [TypeSafe introduction](https://docs.typesafe.ai/introduction),
[primitive contracts](https://docs.typesafe.ai/primitives),
[Python SDK](https://docs.typesafe.ai/sdk/python), and
[launch evidence and caveats](https://typesafe.ai/blog/introducing-system-one-models-and-jev).

## Reasons not to standardize yet

- JEV entered public early access on 2026-09-15, so operational history is very
  short.
- The strongest accuracy, latency and cost evidence currently comes from the
  vendor. TypeSafe explicitly notes potential workflow-author bias and the use of
  other frontier models as reference labels.
- It is an external hosted decision service. Data residency, retention,
  availability, rate limits, support, security attestations and contractual SLOs
  must be reviewed before sensitive workloads are sent.
- Typed output prevents schema hallucination; it does not prove that the selected
  answer is semantically correct.
- Noul has no separate confidence field. OpenModelOps records a clearly labelled
  derived certainty based on distance from 0.5 and must calibrate it independently.

## Promotion experiment

Run JEV in shadow mode on at least 200 independently labelled cases for each
domain. Compare it with deterministic checks, a separately hosted reference
judge and human adjudication. Capture:

- accuracy, precision, recall and Cohen's kappa;
- false-pass rate by risk tier;
- Brier score and reliability curves;
- structured-response validity and provider failures;
- p50/p95/p99 latency, cost and rate-limit behavior;
- agreement with humans and the independent judge;
- drift across provider revisions.

The default qualification policy requires at least 50 cases, 90% accuracy,
false-pass rate no higher than 5%, false-fail rate no higher than 10%, kappa of
at least 0.75 and Brier score no higher than 0.12. High-risk banking or
remediation workflows should use stricter domain-specific thresholds.

Only after the experiment passes may JEV influence routing. It must still never
bypass deterministic policy, RBAC, approval, separation of duties or the narrow
executor allowlist.
