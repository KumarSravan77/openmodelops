# Service-level objectives

| Capability | Initial SLO | Primary indicator |
|---|---:|---|
| Agent API availability | 99.9% monthly | successful eligible requests / eligible requests |
| Agent API latency | 95% under 10 seconds | end-to-end request duration |
| Safety dependency | 99.99% availability | successful guardrail checks |
| Model deployment | 99% under 30 minutes | approved-to-canary duration |
| Training workflow | 99% terminal within declared deadline | completed or explicitly failed runs |
| Lineage completeness | 100% | release has data, code, config and artifact digests |
| Rollback readiness | 100% of production releases | tested previous immutable release |

Error budgets are reviewed weekly. Safety-policy failures are not counted as successful requests, and protected traffic is unavailable rather than served without enforcement.
