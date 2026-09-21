# Streaming Reliability Lab

This workload adds concrete Kafka-compatible reliability engineering to the AI SRE Factory. It is intentionally domain-neutral and uses Redpanda locally as a Kafka API-compatible broker.

## What is implemented

- Eight repeatable failure scenarios: lag, hot partition, rebalance storm, broker failure, schema break, duplicates, poison messages, and healthy baseline.
- Deterministic detection with evidence, safe investigation actions, SLO/error-budget calculation, and Prometheus metrics.
- An ARIA-compatible evidence envelope. The Factory still requires HMAC signing at its ingress; this service never bypasses that trust boundary.
- A customer reliability corrective-action (CRCA) draft that separates observed symptoms from confirmed root cause and requires human approval.
- A follow-the-sun handoff checklist and bounded remediation guidance. No mutation is automatically executed.

## Run locally

```bash
docker compose --profile streaming up -d --build redpanda streaming-api
curl -X POST http://localhost:8011/v1/scenarios/broker-failure
```

Use the returned incident ID to retrieve evidence and a draft CRCA:

```bash
curl "http://localhost:8011/v1/incidents/<incident-id>/aria-evidence?tenant=local"
curl http://localhost:8011/v1/incidents/<incident-id>/crca
```

The evidence payload must be signed by an authorized adapter before posting it to `factory-api:/api/v1/intelligence/aria`.

## Production boundaries

This is a production-style reference and qualification lab, not a claim that a single-node local broker is highly available. Real production needs multi-broker quorum, rack/zone awareness, schema-registry policy, workload identity, encryption, capacity tests, backup/restore exercises, and an organization-specific incident-management integration.
