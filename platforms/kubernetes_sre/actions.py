from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from platforms.kubernetes_sre.client import KubernetesWriter


class ActionType(str, Enum):
    SCALE_DEPLOYMENT = "scale_deployment"
    RESTART_DEPLOYMENT = "restart_deployment"


@dataclass(frozen=True)
class ActionProposal:
    action: ActionType
    cluster: str
    namespace: str
    resource_name: str
    resource_uid: str
    resource_version: str
    requested_by: str
    rationale: str
    rollback: str
    parameters: dict[str, int | str] = field(default_factory=dict)
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def digest(self) -> str:
        payload = asdict(self)
        payload["action"] = self.action.value
        payload["created_at"] = self.created_at.isoformat()
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Approval:
    proposal_id: str
    proposal_digest: str
    approved_by: str
    approved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=15))


class SafetyViolation(ValueError):
    pass


class ChangeExecutor:
    def __init__(self, writer: KubernetesWriter, managed_namespaces: frozenset[str]) -> None:
        self.writer = writer
        self.managed_namespaces = managed_namespaces

    def execute(self, proposal: ActionProposal, approval: Approval, actor: str) -> str:
        now = datetime.now(UTC)
        if proposal.namespace not in self.managed_namespaces:
            raise SafetyViolation("target namespace is outside the managed boundary")
        if not proposal.rollback.strip():
            raise SafetyViolation("rollback instructions are required")
        if approval.proposal_id != proposal.proposal_id or approval.proposal_digest != proposal.digest:
            raise SafetyViolation("approval does not match the immutable proposal")
        if approval.approved_by == proposal.requested_by:
            raise SafetyViolation("proposal author cannot approve their own change")
        if approval.expires_at <= now:
            raise SafetyViolation("approval has expired")
        if actor in {proposal.requested_by, approval.approved_by}:
            raise SafetyViolation("executor must be independent from proposer and approver")
        if proposal.action is ActionType.SCALE_DEPLOYMENT:
            replicas = int(proposal.parameters.get("replicas", -1))
            if not 0 <= replicas <= 100:
                raise SafetyViolation("replicas must be between 0 and 100")
            return self.writer.scale_deployment(
                proposal.namespace, proposal.resource_name, replicas, proposal.resource_uid, proposal.resource_version
            )
        if proposal.action is ActionType.RESTART_DEPLOYMENT:
            return self.writer.restart_deployment(
                proposal.namespace, proposal.resource_name, proposal.resource_uid, proposal.resource_version
            )
        raise SafetyViolation("action is not allowlisted")
