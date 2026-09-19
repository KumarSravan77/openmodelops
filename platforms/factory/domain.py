from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class WorkloadKind(str, Enum):
    MODEL = "model"
    LLM = "llm"
    AGENT = "agent"
    RAG = "rag"


class WorkloadStage(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    PROVISIONED = "provisioned"
    RELEASED = "released"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class SLO:
    availability_target: float
    latency_p95_ms: int
    error_rate_target: float

    def __post_init__(self) -> None:
        if not 0.9 <= self.availability_target < 1:
            raise ValueError("availability_target must be between 0.9 and 1")
        if self.latency_p95_ms <= 0:
            raise ValueError("latency_p95_ms must be positive")
        if not 0 <= self.error_rate_target <= 0.1:
            raise ValueError("error_rate_target must be between 0 and 0.1")


@dataclass(frozen=True)
class FactorySpec:
    name: str
    kind: WorkloadKind
    owner: str
    tenant: str
    environment: str
    artifact_digest: str
    data_classification: str
    slo: SLO
    requires_gpu: bool = False
    internet_egress: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,62}", self.name):
            raise ValueError("name must be a lowercase DNS-compatible identifier")
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("unsupported environment")
        if self.data_classification not in {"public", "internal", "confidential", "restricted"}:
            raise ValueError("unsupported data classification")
        if not self.artifact_digest.startswith("sha256:"):
            raise ValueError("artifact must use an immutable sha256 digest")


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: GateStatus
    evidence: str
    evaluator: str
    evidence_digest: str = ""
    signing_key_id: str = ""
    signature: str = ""
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.evidence.strip():
            raise ValueError("gate evidence is required")


REQUIRED_GATES = frozenset(
    {
        "security",
        "quality",
        "reliability",
        "observability",
        "cost",
        "rollback",
    }
)


@dataclass
class FactoryWorkload:
    spec: FactorySpec
    workload_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: WorkloadStage = WorkloadStage.DRAFT
    gates: dict[str, GateResult] = field(default_factory=dict)
    approved_by: str | None = None
    policy_digest: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    def record_gate(self, result: GateResult) -> None:
        if self.stage not in {WorkloadStage.DRAFT, WorkloadStage.VALIDATED}:
            raise ValueError("gates are immutable after approval")
        if result.gate not in REQUIRED_GATES:
            raise ValueError(f"unsupported release gate: {result.gate}")
        self.gates[result.gate] = result
        self.stage = WorkloadStage.VALIDATED

    def missing_or_failed_gates(self) -> list[str]:
        return sorted(
            gate for gate in REQUIRED_GATES if gate not in self.gates or self.gates[gate].status != GateStatus.PASS
        )

    def approve(self, actor: str, policy_digest: str = "") -> None:
        failures = self.missing_or_failed_gates()
        if self.stage != WorkloadStage.VALIDATED or failures:
            raise ValueError(f"release gates not satisfied: {failures}")
        evaluators = {result.evaluator for result in self.gates.values()}
        if actor == self.spec.owner or actor in evaluators:
            raise ValueError("owner or gate evaluator cannot approve the release")
        self.approved_by = actor
        self.policy_digest = policy_digest or None
        reason = "all required gates passed"
        if policy_digest:
            reason = f"{reason}; policy={policy_digest}"
        self._move(WorkloadStage.APPROVED, actor, reason)

    def provision(self, actor: str) -> None:
        if self.stage != WorkloadStage.APPROVED:
            raise ValueError("only approved workloads may be provisioned")
        self._move(WorkloadStage.PROVISIONED, actor, "platform resources provisioned")

    def release(self, actor: str) -> None:
        if self.stage != WorkloadStage.PROVISIONED:
            raise ValueError("workload must be provisioned before release")
        self._move(WorkloadStage.RELEASED, actor, "workload released")

    def suspend(self, actor: str, reason: str) -> None:
        if self.stage != WorkloadStage.RELEASED or not reason.strip():
            raise ValueError("a released workload and reason are required")
        self._move(WorkloadStage.SUSPENDED, actor, reason)

    def retire(self, actor: str, reason: str) -> None:
        if self.stage not in {WorkloadStage.RELEASED, WorkloadStage.SUSPENDED} or not reason.strip():
            raise ValueError("a released or suspended workload and reason are required")
        self._move(WorkloadStage.RETIRED, actor, reason)

    def scorecard(self) -> dict[str, object]:
        passing = len(REQUIRED_GATES) - len(self.missing_or_failed_gates())
        return {
            "required": len(REQUIRED_GATES),
            "passing": passing,
            "percentage": round(100 * passing / len(REQUIRED_GATES)),
            "blocking_gates": self.missing_or_failed_gates(),
        }

    def _move(self, target: WorkloadStage, actor: str, reason: str) -> None:
        self.history.append(
            {
                "from": self.stage.value,
                "to": target.value,
                "actor": actor,
                "reason": reason,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        self.stage = target
