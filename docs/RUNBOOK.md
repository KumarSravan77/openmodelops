# Operations runbook

## Agent errors or latency

1. Correlate by trace ID and identify agent, prompt revision and model revision.
2. Separate guardrail, model gateway, tool and platform failures.
3. Disable the affected tool or route to the last approved model revision.
4. If quality regressed after release, stop the canary and restore the previous immutable release.
5. Preserve aggregate evidence without copying private prompts into tickets.

## Guardrail outage

Protected agents intentionally become unready and return a dependency-unavailable response. Restore the safety provider or activate a separately approved guardrail implementation. Do not bypass the dependency to restore availability.

## Model drift

1. Confirm data-quality and schema signals before declaring behavioral drift.
2. Compare current traffic with the training/evaluation population by approved slices.
3. Create a new training run; never overwrite the production model.
4. Evaluate, obtain independent approval, deploy as canary and promote only after policy passes.

## Rollback

Select the previous approved artifact digest and release manifest. Apply the deployment change through the normal reviewed pipeline. Verify health, error rate, latency and domain-quality signals; then record the incident and rollback reason in lifecycle history.
