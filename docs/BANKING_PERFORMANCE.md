# Synthetic banking performance evidence

This benchmark exercises a fictional Canadian transaction-risk service. All
accounts and transactions are generated. The workload contains no customer
records, financial institution integration, or claim of regulatory approval.

## Quality gates

| Signal | Gate |
|---|---:|
| Request failure rate | < 1% |
| P95 service latency | < 250 ms |
| P99 service latency | < 500 ms |
| Response contract checks | > 99% |

The service exposes Prometheus request and latency metrics, and k6 writes a raw
JSON summary under `artifacts/performance/`. Raw run artifacts are intentionally
gitignored; this report is the reviewed, durable evidence.

## Pre-fix diagnostic run

Run date: 2026-09-21. Environment: local Docker Compose on a developer machine.

| Result | Observed |
|---|---:|
| Duration | 30 seconds |
| Requests | 98,409 |
| Throughput | 3,280.20 requests/second |
| P95 latency | 0.805 ms |
| P99 latency | 1.285 ms |
| Request failure rate | 0.1016% |

This first run exposed 100 HTTP 422 responses. Investigation identified a load
generator contract defect: early k6 event IDs were shorter than the API's
minimum accepted length. The generator now pads every event ID, and explicit
response-error instrumentation preserves the regression signal. These numbers
are diagnostic evidence and must not be represented as valid capacity results.

## Validated runs

After the event-ID correction, both the rate-controlled smoke test and the
unpaced saturation test passed their executable gates.

| Result | Smoke | Saturation |
|---|---:|---:|
| Completed requests | 150 | 92,710 |
| Failed requests | 0 | 0 |
| Response checks | 100% | 100% |
| P95 latency | 5.970 ms | 0.903 ms |
| P99 latency | not retained | 1.717 ms |

The saturation run experienced a local host/Docker scheduling stall, visible as
a 334.5-second maximum request time and reduced wall-clock throughput. Because
P95/P99 stayed low and no request failed, the run proves contract correctness
under pressure but is not a clean throughput measurement. A production-grade
capacity claim requires repeatable runs on dedicated infrastructure.

## Reproduce

```bash
make banking-up
make banking-smoke
LOAD_PROFILE=saturation make banking-load
```

Production capacity claims require representative infrastructure, independent
load generators, realistic downstream dependencies, longer soak tests, failure
injection, and repeated runs with confidence intervals.
