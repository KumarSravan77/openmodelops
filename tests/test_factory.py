import pytest

from platforms.factory.domain import (
    REQUIRED_GATES,
    SLO,
    FactorySpec,
    FactoryWorkload,
    GateResult,
    GateStatus,
    WorkloadKind,
    WorkloadStage,
)


def factory_workload() -> FactoryWorkload:
    return FactoryWorkload(
        FactorySpec(
            name="risk-agent",
            kind=WorkloadKind.AGENT,
            owner="builder",
            tenant="tenant-a",
            environment="production",
            artifact_digest="sha256:abc123",
            data_classification="restricted",
            slo=SLO(0.999, 750, 0.01),
        )
    )


def test_factory_blocks_release_until_all_evidence_passes() -> None:
    workload = factory_workload()
    workload.record_gate(GateResult("security", GateStatus.PASS, "scan://123", "security-bot"))
    with pytest.raises(ValueError, match="release gates not satisfied"):
        workload.approve("release-manager")
    assert workload.scorecard()["percentage"] == 17


def test_factory_enforces_separation_and_release_sequence() -> None:
    workload = factory_workload()
    for gate in REQUIRED_GATES:
        workload.record_gate(GateResult(gate, GateStatus.PASS, f"evidence://{gate}", f"{gate}-bot"))
    with pytest.raises(ValueError, match="cannot approve"):
        workload.approve("builder")
    workload.approve("release-manager")
    workload.provision("platform-controller")
    workload.release("deployment-controller")
    assert workload.stage == WorkloadStage.RELEASED
    assert workload.scorecard()["percentage"] == 100


def test_factory_requires_immutable_artifact() -> None:
    with pytest.raises(ValueError, match="immutable"):
        FactorySpec(
            name="chat-model",
            kind=WorkloadKind.LLM,
            owner="builder",
            tenant="tenant-a",
            environment="test",
            artifact_digest="latest",
            data_classification="internal",
            slo=SLO(0.99, 1000, 0.02),
        )
