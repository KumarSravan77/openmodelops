from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Workload:
    kind: str
    namespace: str
    name: str
    uid: str
    resource_version: str
    desired_replicas: int = 1
    ready_replicas: int = 0
    restart_count: int = 0
    waiting_reasons: tuple[str, ...] = ()
    images: tuple[str, ...] = ()
    has_readiness_probe: bool = True
    has_liveness_probe: bool = True


@dataclass(frozen=True)
class Autoscaler:
    namespace: str
    name: str
    target: str
    current_replicas: int
    maximum_replicas: int


@dataclass(frozen=True)
class ClusterSnapshot:
    cluster: str
    collected_at: datetime
    workloads: tuple[Workload, ...] = ()
    autoscalers: tuple[Autoscaler, ...] = ()
    namespaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    analyzer: str
    code: str
    severity: Severity
    cluster: str
    namespace: str
    resource: str
    summary: str
    evidence: dict[str, str | int | bool] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        stable = {
            "analyzer": self.analyzer,
            "code": self.code,
            "cluster": self.cluster,
            "namespace": self.namespace,
            "resource": self.resource,
            "evidence": self.evidence,
        }
        return hashlib.sha256(json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class HealthReport:
    cluster: str
    generated_at: datetime
    findings: tuple[Finding, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cluster": self.cluster,
            "generated_at": self.generated_at.astimezone(UTC).isoformat(),
            "findings": [asdict(finding) | {"fingerprint": finding.fingerprint} for finding in self.findings],
        }
