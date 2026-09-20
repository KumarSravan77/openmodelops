from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from platforms.kubernetes_sre.models import ClusterSnapshot, Finding, HealthReport, Severity


class Analyzer(Protocol):
    name: str

    def analyze(self, snapshot: ClusterSnapshot) -> list[Finding]: ...


class WorkloadHealthAnalyzer:
    name = "workload-health"

    def analyze(self, snapshot: ClusterSnapshot) -> list[Finding]:
        findings: list[Finding] = []
        for workload in snapshot.workloads:
            resource = f"{workload.kind.lower()}/{workload.name}"
            if workload.ready_replicas < workload.desired_replicas:
                findings.append(
                    Finding(self.name, "UNDER_REPLICATED", Severity.CRITICAL, snapshot.cluster, workload.namespace,
                            resource, "Workload has fewer ready replicas than desired",
                            {"desired": workload.desired_replicas, "ready": workload.ready_replicas})
                )
            if workload.restart_count >= 5 or {"CrashLoopBackOff", "OOMKilled"} & set(workload.waiting_reasons):
                findings.append(
                    Finding(self.name, "UNHEALTHY_RESTARTS", Severity.CRITICAL, snapshot.cluster, workload.namespace,
                            resource, "Workload is repeatedly restarting",
                            {"restart_count": workload.restart_count, "reasons": ",".join(workload.waiting_reasons)})
                )
        return findings


class ReliabilityAnalyzer:
    name = "reliability"

    def analyze(self, snapshot: ClusterSnapshot) -> list[Finding]:
        findings: list[Finding] = []
        for workload in snapshot.workloads:
            resource = f"{workload.kind.lower()}/{workload.name}"
            missing = []
            if not workload.has_readiness_probe:
                missing.append("readiness")
            if not workload.has_liveness_probe:
                missing.append("liveness")
            if missing:
                findings.append(
                    Finding(self.name, "MISSING_HEALTH_PROBES", Severity.WARNING, snapshot.cluster,
                            workload.namespace, resource, "Workload is missing health probes",
                            {"missing": ",".join(missing)})
                )
            if any(image.endswith(":latest") or ":" not in image.rsplit("/", 1)[-1] for image in workload.images):
                findings.append(
                    Finding(self.name, "MUTABLE_IMAGE_TAG", Severity.WARNING, snapshot.cluster,
                            workload.namespace, resource, "Workload uses an unpinned container image",
                            {"images": ",".join(workload.images)})
                )
        return findings


class ScalingAnalyzer:
    name = "scaling"

    def analyze(self, snapshot: ClusterSnapshot) -> list[Finding]:
        return [
            Finding(self.name, "HPA_AT_MAX", Severity.WARNING, snapshot.cluster, hpa.namespace, f"hpa/{hpa.name}",
                    "Autoscaler is at its configured maximum",
                    {"current": hpa.current_replicas, "maximum": hpa.maximum_replicas, "target": hpa.target})
            for hpa in snapshot.autoscalers
            if hpa.maximum_replicas > 0 and hpa.current_replicas >= hpa.maximum_replicas
        ]


class ParallelAnalyzer:
    """Runs deterministic specialists concurrently; no LLM is used in scheduled health collection."""

    def __init__(self, analyzers: tuple[Analyzer, ...] | None = None, max_workers: int = 3) -> None:
        self.analyzers = analyzers or (WorkloadHealthAnalyzer(), ReliabilityAnalyzer(), ScalingAnalyzer())
        self.max_workers = min(max_workers, len(self.analyzers))

    def analyze(self, snapshot: ClusterSnapshot) -> HealthReport:
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="sre-analyzer") as pool:
            batches = list(pool.map(lambda analyzer: analyzer.analyze(snapshot), self.analyzers))
        findings = sorted((item for batch in batches for item in batch), key=lambda item: item.fingerprint)
        return HealthReport(snapshot.cluster, snapshot.collected_at, tuple(findings))
