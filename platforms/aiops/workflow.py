from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class IncidentState(str, Enum):
    DETECTED = "detected"
    CORRELATED = "correlated"
    INVESTIGATING = "investigating"
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class Signal:
    source: str
    service: str
    severity: str
    fingerprint: str
    observed_at: datetime
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Remediation:
    action: str
    target: str
    rationale: str
    risk: str
    rollback: str
    side_effecting: bool = True


@dataclass
class Incident:
    service: str
    signals: list[Signal]
    incident_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: IncidentState = IncidentState.DETECTED
    recommendation: Remediation | None = None
    approved_by: str | None = None
    audit: list[dict[str, str]] = field(default_factory=list)

    def correlate(self, actor: str) -> None:
        if self.state != IncidentState.DETECTED or any(signal.service != self.service for signal in self.signals):
            raise ValueError("incident signals cannot be correlated")
        self._move(IncidentState.CORRELATED, actor, "signals correlated by service")

    def investigate(self, actor: str) -> None:
        if self.state != IncidentState.CORRELATED:
            raise ValueError("incident must be correlated first")
        self._move(IncidentState.INVESTIGATING, actor, "investigation started")

    def recommend(self, remediation: Remediation, actor: str) -> None:
        if self.state != IncidentState.INVESTIGATING:
            raise ValueError("incident must be under investigation")
        if remediation.side_effecting and (
            not remediation.rollback or remediation.risk not in {"low", "medium", "high"}
        ):
            raise ValueError("side-effecting remediation requires risk and rollback")
        self.recommendation = remediation
        self._move(IncidentState.RECOMMENDED, actor, remediation.rationale)

    def approve(self, approver: str) -> None:
        if self.state != IncidentState.RECOMMENDED:
            raise ValueError("only a recommendation can be approved")
        if any(entry["actor"] == approver and entry["to"] == IncidentState.RECOMMENDED.value for entry in self.audit):
            raise ValueError("recommendation author cannot approve remediation")
        self.approved_by = approver
        self._move(IncidentState.APPROVED, approver, "remediation approved")

    def execute(self, actor: str) -> None:
        if self.state != IncidentState.APPROVED or self.recommendation is None:
            raise ValueError("approved remediation required")
        self._move(IncidentState.EXECUTING, actor, self.recommendation.action)

    def verify(self, healthy: bool, actor: str) -> None:
        if self.state != IncidentState.EXECUTING:
            raise ValueError("execution must precede verification")
        self._move(IncidentState.VERIFYING, actor, "post-action verification")
        self._move(
            IncidentState.RESOLVED if healthy else IncidentState.ESCALATED,
            actor,
            "service recovered" if healthy else "verification failed",
        )

    def _move(self, target: IncidentState, actor: str, reason: str) -> None:
        self.audit.append(
            {
                "from": self.state.value,
                "to": target.value,
                "actor": actor,
                "reason": reason,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        self.state = target
