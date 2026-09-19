from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class RunState(str, Enum):
    CREATED = "created"
    TRAINING = "training"
    EVALUATING = "evaluating"
    REJECTED = "rejected"
    CANDIDATE = "candidate"
    APPROVED = "approved"
    DEPLOYING = "deploying"
    CANARY = "canary"
    PRODUCTION = "production"
    ROLLED_BACK = "rolled_back"
    RETIRED = "retired"


_TRANSITIONS = {
    RunState.CREATED: {RunState.TRAINING},
    RunState.TRAINING: {RunState.EVALUATING},
    RunState.EVALUATING: {RunState.REJECTED, RunState.CANDIDATE},
    RunState.CANDIDATE: {RunState.APPROVED, RunState.REJECTED},
    RunState.APPROVED: {RunState.DEPLOYING},
    RunState.DEPLOYING: {RunState.CANARY, RunState.ROLLED_BACK},
    RunState.CANARY: {RunState.PRODUCTION, RunState.ROLLED_BACK},
    RunState.PRODUCTION: {RunState.ROLLED_BACK, RunState.RETIRED},
    RunState.ROLLED_BACK: {RunState.RETIRED},
    RunState.REJECTED: set(),
    RunState.RETIRED: set(),
}


@dataclass(frozen=True)
class EvaluationPolicy:
    minimum_metrics: Mapping[str, float]
    maximum_metrics: Mapping[str, float] = field(default_factory=dict)

    def evaluate(self, metrics: Mapping[str, float]) -> tuple[bool, list[str]]:
        failures = [
            f"{name}={metrics.get(name)!r} below {threshold}"
            for name, threshold in self.minimum_metrics.items()
            if metrics.get(name, float("-inf")) < threshold
        ]
        failures.extend(
            f"{name}={metrics.get(name)!r} above {threshold}"
            for name, threshold in self.maximum_metrics.items()
            if metrics.get(name, float("inf")) > threshold
        )
        return not failures, failures


@dataclass
class ModelRun:
    run_id: str
    model_name: str
    dataset_digest: str
    code_revision: str
    owner: str
    state: RunState = RunState.CREATED
    artifact_digest: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    approver: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    def transition(self, target: RunState, actor: str, reason: str) -> None:
        if target not in _TRANSITIONS[self.state]:
            raise ValueError(f"invalid transition {self.state.value} -> {target.value}")
        if target == RunState.APPROVED:
            if actor == self.owner:
                raise ValueError("separation of duties: run owner cannot approve their own model")
            if not reason.strip():
                raise ValueError("approval requires a reason")
            self.approver = actor
        self.history.append(
            {
                "from": self.state.value,
                "to": target.value,
                "actor": actor,
                "reason": reason,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        self.state = target

    def record_evaluation(
        self, metrics: Mapping[str, float], artifact_digest: str, policy: EvaluationPolicy, actor: str
    ) -> bool:
        if self.state != RunState.EVALUATING:
            raise ValueError("evaluation results can only be recorded in evaluating state")
        if not artifact_digest.startswith("sha256:"):
            raise ValueError("artifact must use a sha256 digest")
        self.metrics = dict(metrics)
        self.artifact_digest = artifact_digest
        passed, failures = policy.evaluate(metrics)
        self.transition(
            RunState.CANDIDATE if passed else RunState.REJECTED,
            actor,
            "quality gates passed" if passed else "; ".join(failures),
        )
        return passed
