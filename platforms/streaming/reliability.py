from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class StreamingSnapshot(BaseModel):
    cluster: str = "local-redpanda"
    workload_id: str = "streaming-reference"
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    produced_total: int = Field(ge=0)
    consumed_total: int = Field(ge=0)
    consumer_lag: int = Field(ge=0)
    partition_lag: dict[str, int] = Field(default_factory=dict)
    rebalances_5m: int = Field(default=0, ge=0)
    under_replicated_partitions: int = Field(default=0, ge=0)
    offline_partitions: int = Field(default=0, ge=0)
    schema_errors_5m: int = Field(default=0, ge=0)
    duplicate_rate: float = Field(default=0, ge=0, le=1)
    dlq_rate: float = Field(default=0, ge=0, le=1)
    disk_used_percent: float = Field(default=0, ge=0, le=100)
    p99_latency_ms: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_partition_lag(self) -> StreamingSnapshot:
        if any(value < 0 for value in self.partition_lag.values()):
            raise ValueError("partition lag cannot be negative")
        return self


class Finding(BaseModel):
    code: str
    severity: Severity
    summary: str
    evidence: dict[str, object]
    safe_actions: list[str]


class SLOAssessment(BaseModel):
    target: float
    availability: float
    error_budget_fraction: float
    budget_consumed_percent: float
    burn_rate: float
    status: str


class StreamingAssessment(BaseModel):
    incident_id: str
    cluster: str
    workload_id: str
    observed_at: datetime
    severity: Severity
    findings: list[Finding]
    slo: SLOAssessment
    evidence_digest: str
    automatic_remediation: bool = False

    def aria_evidence(self, tenant: str) -> dict[str, object]:
        """Return the signed-ingress payload shape accepted by the Factory ARIA adapter."""
        return {
            "source": "aria",
            "schema_version": "1.0",
            "signal_id": self.incident_id,
            "tenant": tenant,
            "workload_id": self.workload_id,
            "severity": self.severity.value,
            "confidence": 1.0 if self.findings else 0.8,
            "observed_at": self.observed_at.isoformat(),
            "evidence_digest": self.evidence_digest,
            "finding_codes": [finding.code for finding in self.findings],
            "slo": self.slo.model_dump(),
            "automatic_remediation": False,
        }


SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def assess_slo(snapshot: StreamingSnapshot, target: float = 0.999) -> SLOAssessment:
    if not 0 < target < 1:
        raise ValueError("SLO target must be between zero and one")
    if snapshot.produced_total == 0:
        availability = 1.0
    else:
        availability = min(snapshot.consumed_total, snapshot.produced_total) / snapshot.produced_total
    observed_error = 1 - availability
    allowed_error = 1 - target
    burn_rate = observed_error / allowed_error
    consumed = max(0.0, observed_error / allowed_error * 100)
    return SLOAssessment(
        target=target,
        availability=round(availability, 6),
        error_budget_fraction=round(allowed_error, 6),
        budget_consumed_percent=round(consumed, 2),
        burn_rate=round(burn_rate, 2),
        status="exhausted" if consumed >= 100 else "at-risk" if consumed >= 50 else "healthy",
    )


def diagnose(snapshot: StreamingSnapshot, target: float = 0.999) -> StreamingAssessment:
    findings: list[Finding] = []

    def add(code: str, severity: Severity, summary: str, evidence: dict, actions: list[str]) -> None:
        findings.append(Finding(code=code, severity=severity, summary=summary, evidence=evidence, safe_actions=actions))

    if snapshot.offline_partitions:
        add("OFFLINE_PARTITIONS", Severity.CRITICAL, "Partitions are unavailable.",
            {"offline_partitions": snapshot.offline_partitions},
            ["Page the streaming incident commander", "Inspect broker and quorum health", "Pause unsafe releases"])
    if snapshot.under_replicated_partitions:
        add("UNDER_REPLICATED_PARTITIONS", Severity.HIGH, "Replication durability is degraded.",
            {"under_replicated_partitions": snapshot.under_replicated_partitions},
            ["Inspect broker health and disk pressure", "Confirm replica recovery before changing replication"])
    if snapshot.consumer_lag >= 10_000:
        add("CONSUMER_LAG", Severity.HIGH, "Consumer processing is materially behind production.",
            {"consumer_lag": snapshot.consumer_lag},
            ["Inspect consumer errors and saturation", "Scale only after confirming partition parallelism"])
    lags = list(snapshot.partition_lag.values())
    if lags and max(lags) >= 1_000 and max(lags) > 2 * max(sum(lags) / len(lags), 1):
        hot = max(snapshot.partition_lag, key=snapshot.partition_lag.get)  # type: ignore[arg-type]
        add("HOT_PARTITION", Severity.HIGH, "One partition carries disproportionate lag.",
            {"partition": hot, "lag": snapshot.partition_lag[hot], "mean_lag": round(sum(lags) / len(lags), 2)},
            ["Inspect key cardinality and partition assignment", "Plan a compatible repartitioning migration"])
    if snapshot.rebalances_5m >= 5:
        add("REBALANCE_STORM", Severity.MEDIUM, "The consumer group is repeatedly rebalancing.",
            {"rebalances_5m": snapshot.rebalances_5m},
            ["Inspect membership churn and heartbeat timeouts", "Stabilize deployments before scaling"])
    if snapshot.schema_errors_5m:
        add("SCHEMA_INCOMPATIBILITY", Severity.HIGH, "Messages are failing schema validation.",
            {"schema_errors_5m": snapshot.schema_errors_5m},
            ["Stop the incompatible producer rollout", "Validate compatibility and replay quarantined records"])
    if snapshot.duplicate_rate > 0.001:
        add("DUPLICATE_PROCESSING", Severity.HIGH, "Observed duplicates exceed the idempotency SLO.",
            {"duplicate_rate": snapshot.duplicate_rate},
            ["Verify idempotency keys and transaction boundaries", "Reconcile downstream side effects"])
    if snapshot.dlq_rate > 0.01:
        add("POISON_MESSAGES", Severity.MEDIUM, "Dead-letter traffic exceeds the operating threshold.",
            {"dlq_rate": snapshot.dlq_rate},
            ["Sample redacted DLQ records", "Fix parser safely before controlled replay"])
    if snapshot.disk_used_percent >= 85:
        add("DISK_PRESSURE", Severity.HIGH, "Broker disk utilization threatens retention and availability.",
            {"disk_used_percent": snapshot.disk_used_percent},
            ["Page storage owner", "Verify retention and tiered-storage health", "Add capacity through an approved change"])
    if snapshot.p99_latency_ms >= 1_000:
        add("LATENCY_SLO", Severity.MEDIUM, "End-to-end event latency is outside the service objective.",
            {"p99_latency_ms": snapshot.p99_latency_ms},
            ["Inspect broker, network, and consumer latency spans", "Correlate with deploy and saturation events"])

    slo = assess_slo(snapshot, target)
    if slo.status == "exhausted":
        add("ERROR_BUDGET_EXHAUSTED", Severity.HIGH, "The streaming availability error budget is exhausted.",
            {"burn_rate": slo.burn_rate, "availability": slo.availability, "target": slo.target},
            ["Freeze non-remediation changes", "Open a reliability review with accountable owners"])

    severity = max((finding.severity for finding in findings), key=SEVERITY_RANK.get, default=Severity.INFO)
    evidence = snapshot.model_dump(mode="json")
    digest = "sha256:" + hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    incident_id = "stream-" + digest.removeprefix("sha256:")[:16]
    return StreamingAssessment(
        incident_id=incident_id,
        cluster=snapshot.cluster,
        workload_id=snapshot.workload_id,
        observed_at=snapshot.observed_at,
        severity=severity,
        findings=findings,
        slo=slo,
        evidence_digest=digest,
    )


def render_crca(assessment: StreamingAssessment) -> str:
    evidence = "\n".join(
        f"- `{item.code}` ({item.severity.value}): {item.summary} Evidence: `{json.dumps(item.evidence, sort_keys=True)}`"
        for item in assessment.findings
    ) or "- No threshold violations detected."
    actions = "\n".join(
        f"- [ ] {action} (owner and due date required)"
        for action in dict.fromkeys(action for item in assessment.findings for action in item.safe_actions)
    ) or "- [ ] Continue routine monitoring."
    return f"""# Customer Reliability Corrective Action — DRAFT

Incident: `{assessment.incident_id}`  
Cluster: `{assessment.cluster}`  
Severity: **{assessment.severity.value}**  
Evidence digest: `{assessment.evidence_digest}`

## Customer impact

To be confirmed by the incident commander from customer and business telemetry. Do not infer impact from infrastructure signals alone.

## Detection and evidence

{evidence}

## Root cause

Not yet established. This draft records symptoms and must not present correlation as causation.

## Corrective and preventive actions

{actions}

## Follow-the-sun handoff

- Current incident commander: unassigned
- Active hypothesis and disconfirming evidence: required
- Changes made and rollback state: required
- Next checkpoint, owner, and escalation path: required

## Approval

Human technical review and communications approval are required before customer publication.
"""
