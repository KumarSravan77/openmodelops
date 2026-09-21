# Synthetic Canadian banking benchmark

This workload uses generated accounts and transactions only. It is not connected
to a real financial institution and does not claim regulatory certification.

Profiles cover smoke, baseline, load, spike, soak and saturation traffic. Smoke
is intentionally rate-controlled; saturation is the explicit maximum-throughput
experiment. The default quality
gate requires less than 1% request failures, P95 below 250 ms, P99 below 500 ms,
and more than 99% successful response checks.

```bash
make banking-up
make banking-smoke
LOAD_PROFILE=load make banking-load
LOAD_PROFILE=saturation make banking-load
```

Generate a deterministic replay dataset:

```bash
python3 -m performance.banking.generator --count 100000 \
  --output artifacts/performance/banking-transactions.ndjson
```

The account identifiers are random opaque tokens. Raw personal names, addresses,
government identifiers and real account data are intentionally absent.
