from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platforms.kubernetes_sre.actions import ActionProposal, ActionType, Approval, ChangeExecutor, SafetyViolation
from platforms.kubernetes_sre.analyzers import ParallelAnalyzer
from platforms.kubernetes_sre.models import Autoscaler, ClusterSnapshot, Severity, Workload
from platforms.kubernetes_sre.service import KubernetesSREService
from platforms.kubernetes_sre.store import SREStore


class FakeReader:
    def __init__(self, snapshot: ClusterSnapshot) -> None:
        self.value = snapshot
        self.calls = 0

    def snapshot(self, cluster: str) -> ClusterSnapshot:
        self.calls += 1
        assert cluster == self.value.cluster
        return self.value


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def scale_deployment(self, namespace, name, replicas, expected_uid, expected_resource_version):
        self.calls.append(("scale", namespace, name, replicas, expected_uid, expected_resource_version))
        return "rv-2"

    def restart_deployment(self, namespace, name, expected_uid, expected_resource_version):
        self.calls.append(("restart", namespace, name, expected_uid, expected_resource_version))
        return "rv-2"


@pytest.fixture
def snapshot() -> ClusterSnapshot:
    return ClusterSnapshot(
        cluster="test",
        collected_at=datetime.now(UTC),
        workloads=(
            Workload(
                kind="Deployment",
                namespace="openmodelops-managed",
                name="payments",
                uid="uid-1",
                resource_version="rv-1",
                desired_replicas=3,
                ready_replicas=1,
                restart_count=7,
                waiting_reasons=("CrashLoopBackOff",),
                images=("example/payments:latest",),
                has_liveness_probe=False,
            ),
        ),
        autoscalers=(Autoscaler("openmodelops-managed", "payments", "payments", 10, 10),),
        namespaces=("openmodelops-managed",),
    )


def make_proposal(requested_by: str = "proposer", **changes) -> ActionProposal:
    values = {
        "action": ActionType.SCALE_DEPLOYMENT,
        "cluster": "test",
        "namespace": "openmodelops-managed",
        "resource_name": "payments",
        "resource_uid": "uid-1",
        "resource_version": "rv-1",
        "requested_by": requested_by,
        "rationale": "restore service capacity",
        "rollback": "scale back to three replicas",
        "parameters": {"replicas": 5},
    }
    values.update(changes)
    return ActionProposal(**values)


def test_parallel_analysis_is_deterministic_and_detects_failures(snapshot):
    analyzer = ParallelAnalyzer()
    first = analyzer.analyze(snapshot)
    second = analyzer.analyze(snapshot)
    assert [item.fingerprint for item in first.findings] == [item.fingerprint for item in second.findings]
    assert {item.code for item in first.findings} == {
        "UNDER_REPLICATED", "UNHEALTHY_RESTARTS", "MISSING_HEALTH_PROBES", "MUTABLE_IMAGE_TAG", "HPA_AT_MAX"
    }
    assert all(item.severity in {Severity.CRITICAL, Severity.WARNING} for item in first.findings)


def test_scheduled_inspection_uses_reader_and_persists_without_llm(tmp_path, snapshot):
    reader = FakeReader(snapshot)
    store = SREStore(str(tmp_path / "sre.db"))
    service = KubernetesSREService(reader, ParallelAnalyzer(), store)
    report = service.inspect("test")
    assert reader.calls == 1
    assert len(report.findings) == 5
    assert store.connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0] == 1


def test_action_requires_matching_independent_unexpired_approval():
    writer = FakeWriter()
    executor = ChangeExecutor(writer, frozenset({"openmodelops-managed"}))
    proposal = make_proposal()
    approval = Approval(proposal.proposal_id, proposal.digest, "approver")
    assert executor.execute(proposal, approval, "executor") == "rv-2"
    assert writer.calls[0][:4] == ("scale", "openmodelops-managed", "payments", 5)


@pytest.mark.parametrize(
    "approval,actor,message",
    [
        (lambda p: Approval(p.proposal_id, "tampered", "approver"), "executor", "does not match"),
        (lambda p: Approval(p.proposal_id, p.digest, "proposer"), "executor", "cannot approve"),
        (lambda p: Approval(p.proposal_id, p.digest, "approver", expires_at=datetime.now(UTC) - timedelta(seconds=1)),
         "executor", "expired"),
        (lambda p: Approval(p.proposal_id, p.digest, "approver"), "approver", "independent"),
    ],
)
def test_action_rejects_invalid_approval(approval, actor, message):
    proposal = make_proposal()
    executor = ChangeExecutor(FakeWriter(), frozenset({"openmodelops-managed"}))
    with pytest.raises(SafetyViolation, match=message):
        executor.execute(proposal, approval(proposal), actor)


def test_action_rejects_namespace_and_replica_escape():
    executor = ChangeExecutor(FakeWriter(), frozenset({"openmodelops-managed"}))
    outside = make_proposal(namespace="kube-system")
    with pytest.raises(SafetyViolation, match="outside"):
        executor.execute(outside, Approval(outside.proposal_id, outside.digest, "approver"), "executor")
    excessive = make_proposal(parameters={"replicas": 101})
    with pytest.raises(SafetyViolation, match="between"):
        executor.execute(excessive, Approval(excessive.proposal_id, excessive.digest, "approver"), "executor")


def test_store_survives_reopen_and_enforces_single_approval(tmp_path):
    path = str(tmp_path / "sre.db")
    proposal = make_proposal()
    SREStore(path).save_proposal(proposal)
    reopened = SREStore(path)
    restored = reopened.get_proposal(proposal.proposal_id)
    assert restored.digest == proposal.digest
    approval = Approval(proposal.proposal_id, proposal.digest, "approver")
    reopened.approve(approval)
    with pytest.raises(ValueError, match="already approved"):
        reopened.approve(approval)


def test_service_separates_proposal_approval_and_execution(tmp_path, snapshot):
    writer = FakeWriter()
    store = SREStore(str(tmp_path / "sre.db"))
    service = KubernetesSREService(
        FakeReader(snapshot), ParallelAnalyzer(), store,
        ChangeExecutor(writer, frozenset({"openmodelops-managed"})),
    )
    proposal = service.propose(make_proposal())
    with pytest.raises(ValueError, match="cannot approve"):
        service.approve(proposal.proposal_id, "proposer")
    service.approve(proposal.proposal_id, "approver")
    assert service.execute(proposal.proposal_id, "executor") == "rv-2"
    with pytest.raises(ValueError, match="already claimed"):
        service.execute(proposal.proposal_id, "another-executor")
