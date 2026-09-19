import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from platforms.factory.domain import SLO, FactorySpec, FactoryWorkload, WorkloadKind
from platforms.factory.governance import EvidenceStatement, EvidenceVerifier, FactoryPolicy
from platforms.factory.store import ConcurrencyError, FactoryStore


def workload(tenant: str = "tenant-a") -> FactoryWorkload:
    return FactoryWorkload(
        FactorySpec(
            name="fraud-model",
            kind=WorkloadKind.MODEL,
            owner="ml-engineer",
            tenant=tenant,
            environment="production",
            artifact_digest="sha256:abc",
            data_classification="restricted",
            slo=SLO(0.999, 500, 0.01),
        )
    )


def test_store_is_durable_tenant_scoped_and_optimistic(tmp_path) -> None:
    store = FactoryStore(f"sqlite:///{tmp_path / 'factory.db'}")
    item = workload()
    assert store.create(item) == 1
    assert store.ready()
    assert store.get(item.workload_id, "other-tenant") is None
    restored, version = store.get(item.workload_id, "tenant-a") or (None, None)
    assert restored is not None
    assert restored.spec.artifact_digest == "sha256:abc"
    assert store.save(restored, version) == 2
    with pytest.raises(ConcurrencyError):
        store.save(restored, version)


def test_signed_evidence_verification() -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    statement = EvidenceStatement(
        workload_id="workload-1",
        gate="security",
        evidence_uri="oci://evidence/security@sha256:abc",
        evidence_digest="sha256:abc",
        evaluator="security-bot",
    )
    signature = base64.b64encode(private_key.sign(statement.canonical_bytes())).decode()
    EvidenceVerifier({"security-key": public_key}).verify(statement, "security-key", signature)
    with pytest.raises(ValueError, match="verification failed"):
        EvidenceVerifier({"security-key": public_key}).verify(
            statement, "security-key", base64.b64encode(b"bad").decode()
        )


def test_policy_blocks_restricted_production_egress() -> None:
    item = workload()
    unsafe_spec = FactorySpec(**{**item.spec.__dict__, "internet_egress": True})
    decision = FactoryPolicy().evaluate(unsafe_spec)
    assert not decision.allowed
    assert decision.policy_digest.startswith("sha256:")
    assert len(decision.reasons) == 2


def test_approval_records_policy_generation() -> None:
    item = workload()
    from platforms.factory.domain import REQUIRED_GATES, GateResult, GateStatus

    for gate in REQUIRED_GATES:
        item.record_gate(GateResult(gate, GateStatus.PASS, f"file:///{gate}.json", f"{gate}-bot"))
    decision = FactoryPolicy().evaluate(item.spec)
    item.approve("release-manager", decision.policy_digest)
    assert item.policy_digest == decision.policy_digest
    assert decision.policy_digest in item.history[-1]["reason"]
