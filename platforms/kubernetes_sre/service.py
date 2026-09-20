from __future__ import annotations

from contextlib import nullcontext

from prometheus_client import Counter, Histogram

from packages.observability.telemetry import OpikTelemetry, Telemetry
from platforms.kubernetes_sre.actions import ActionProposal, Approval, ChangeExecutor
from platforms.kubernetes_sre.analyzers import ParallelAnalyzer
from platforms.kubernetes_sre.client import KubernetesReader
from platforms.kubernetes_sre.models import HealthReport
from platforms.kubernetes_sre.store import SREStore

INSPECTIONS = Counter("openmodelops_sre_inspections_total", "Kubernetes inspections", ["cluster", "outcome"])
FINDINGS = Counter("openmodelops_sre_findings_total", "Kubernetes findings", ["cluster", "severity", "code"])
INSPECTION_SECONDS = Histogram("openmodelops_sre_inspection_duration_seconds", "Kubernetes inspection duration")
ACTIONS = Counter("openmodelops_sre_actions_total", "Kubernetes remediation actions", ["action", "outcome"])


class KubernetesSREService:
    def __init__(
        self,
        reader: KubernetesReader,
        analyzer: ParallelAnalyzer,
        store: SREStore,
        executor: ChangeExecutor | None = None,
        telemetry: Telemetry | OpikTelemetry | None = None,
    ) -> None:
        self.reader = reader
        self.analyzer = analyzer
        self.store = store
        self.executor = executor
        self.telemetry = telemetry

    def inspect(self, cluster: str) -> HealthReport:
        span = self.telemetry.operation("sre", attributes={"sre.cluster": cluster, "sre.operation": "inspect"}) if self.telemetry else nullcontext()
        try:
            with INSPECTION_SECONDS.time(), span:
                report = self.analyzer.analyze(self.reader.snapshot(cluster))
                self.store.save_report(report.to_dict())
            INSPECTIONS.labels(cluster, "success").inc()
            for finding in report.findings:
                FINDINGS.labels(cluster, finding.severity.value, finding.code).inc()
            return report
        except Exception:
            INSPECTIONS.labels(cluster, "error").inc()
            raise

    def propose(self, proposal: ActionProposal) -> ActionProposal:
        self.store.save_proposal(proposal)
        return proposal

    def approve(self, proposal_id: str, approver: str) -> Approval:
        proposal = self.store.get_proposal(proposal_id)
        if proposal.requested_by == approver:
            raise ValueError("proposal author cannot approve their own change")
        approval = Approval(proposal.proposal_id, proposal.digest, approver)
        self.store.approve(approval)
        return approval

    def execute(self, proposal_id: str, actor: str) -> str:
        if self.executor is None:
            raise RuntimeError("change execution is disabled")
        proposal = self.store.get_proposal(proposal_id)
        approval = self.store.get_approval(proposal_id)
        self.store.claim_execution(proposal_id)
        try:
            result = self.executor.execute(proposal, approval, actor)
            self.store.finish_execution(proposal_id, succeeded=True)
            ACTIONS.labels(proposal.action.value, "success").inc()
            return result
        except Exception:
            self.store.finish_execution(proposal_id, succeeded=False)
            ACTIONS.labels(proposal.action.value, "error").inc()
            raise
