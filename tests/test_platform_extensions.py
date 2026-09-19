from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from packages.security.auth import AuthorizationError, Identity, require_roles
from packages.security.fastapi_auth import current_identity
from platforms.aiops.workflow import Incident, IncidentState, Remediation, Signal
from platforms.features.contracts import FeatureContractError, FeatureDefinition, FeatureRecord, FeatureService
from platforms.retrieval.vector_store import QdrantStore
from platforms.training.spec import ResourceSpec, TrainingSpec, ray_job


def test_rbac_is_fail_closed() -> None:
    identity = Identity("operator-1", frozenset({"viewer"}), "tenant-a")
    with pytest.raises(AuthorizationError):
        require_roles("release-approver")(identity)


def test_development_identity_is_disabled_in_production(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("FACTORY_ENV", "production")
    with pytest.raises(HTTPException) as error:
        current_identity(None)
    assert error.value.status_code == 503


def test_feature_contract_rejects_drift_and_future_data() -> None:
    service = FeatureService([FeatureDefinition("risk_score", "float", "risk", "score", 0, 1)])
    service.validate(FeatureRecord("account-1", datetime.now(UTC), {"risk_score": 0.7}))
    with pytest.raises(FeatureContractError):
        service.validate(FeatureRecord("account-1", datetime.now(UTC), {"risk_score": 1.2}))
    with pytest.raises(FeatureContractError):
        FeatureRecord("account-1", datetime.now(UTC) + timedelta(hours=1), {"risk_score": 0.2})


def test_ray_job_uses_immutable_inputs_and_gpu_requests() -> None:
    spec = TrainingSpec(
        run_id="run-123",
        image_digest="sha256:abc",
        dataset_uri="s3://datasets/training.parquet",
        dataset_digest="sha256:def",
        entrypoint="python train.py",
        resources=ResourceSpec(workers=2, gpu_per_worker=1),
    )
    body = ray_job(spec)
    workers = body["spec"]["rayClusterSpec"]["workerGroupSpecs"][0]
    assert workers["replicas"] == 2
    assert workers["template"]["spec"]["containers"][0]["resources"]["requests"]["nvidia.com/gpu"] == "1"


def test_training_spec_blocks_plaintext_secret_environment() -> None:
    with pytest.raises(ValueError):
        TrainingSpec("run", "sha256:a", "s3://data", "sha256:b", "train", environment={"API_TOKEN": "bad"})


def test_vector_search_requires_tenant() -> None:
    store = QdrantStore("http://qdrant:6333", "documents")
    with pytest.raises(ValueError):
        store.search([0.1, 0.2], tenant="", limit=5)


def test_aiops_requires_independent_approval_and_verifies_recovery() -> None:
    signal = Signal("prometheus", "inference", "critical", "latency", datetime.now(UTC))
    incident = Incident("inference", [signal])
    incident.correlate("correlator-agent")
    incident.investigate("diagnostic-agent")
    incident.recommend(
        Remediation("restart deployment", "inference", "unhealthy replicas", "low", "undo rollout"),
        "planner-agent",
    )
    with pytest.raises(ValueError):
        incident.approve("planner-agent")
    incident.approve("human-operator")
    incident.execute("runbook-executor")
    incident.verify(True, "health-verifier")
    assert incident.state == IncidentState.RESOLVED
    assert len(incident.audit) == 7
