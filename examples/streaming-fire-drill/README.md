# Cross-Repository Streaming Fire Drill

This demonstration joins three independently deployable projects through one
versioned evidence chain:

```text
Fire Drill (approved fault injection and immutable plan digest)
  -> OpenModelOps (streaming SLO, error-budget and symptom evaluation)
  -> ARIA (read-only Kafka investigation and governed incident evidence)
```

## Safety and ownership

- Fire Drill is the only component permitted to inject a failure.
- OpenModelOps evaluates observations and never mutates the broker.
- ARIA investigates and recommends; its Kafka agent has no topic, ACL, broker,
  or consumer-group mutation capability.
- `experiment_id`, `event_id`, `plan_digest`, and `evidence_digest` remain in
  the result for audit correlation.
- Live execution remains development/staging only and approval-gated.
- The fixture's approver field is sample data; only Fire Drill's audited agent
  run can establish actual approval and execution.
- The shared contract explicitly marks this run as `synthetic` and rejects an
  unverified live claim.

## Local contract test

With the three repositories checked out as siblings, run from OpenModelOps:

```bash
python3 examples/streaming-fire-drill/run_contract_demo.py \
  --fire-drill-python /usr/bin/python3 \
  --openmodelops-python .venv/bin/python \
  --aria-python /usr/bin/python3
```

The script builds a Fire Drill envelope from `plan.json`, `snapshot.json`, and
`observation.json`,
evaluates it through OpenModelOps, and calls ARIA's Kafka investigation function.
It verifies that experiment, plan, and observation digests survive every hop.
The output preserves Fire Drill's resilience/detection/recovery report with
12-second synthetic detection and 45-second synthetic recovery, separately
from OpenModelOps' on-time completion SLO.
The sample Fire Drill report passes its generic availability/error/recovery
checks while the streaming SLO is exhausted, so the combined qualification
verdict is `ACTION_REQUIRED`.
For deployed services, the same contracts are exposed by OpenModelOps at
`POST /v1/fire-drills/evaluate` and by ARIA at its authenticated
`POST /integrations/fire-drill/streaming` endpoint.

This synthetic run proves contract wiring. A live qualification requires a sandbox
cluster, measured before/during/after telemetry, rollback verification, and a
reviewed resilience report.
