from fastapi.testclient import TestClient

from platforms.streaming.api import RECENT, app
from platforms.streaming.reliability import StreamingSnapshot, assess_slo, diagnose, render_crca

client = TestClient(app)


def test_all_qualification_scenarios_run() -> None:
    expected = {
        "healthy": set(),
        "consumer-lag": {"CONSUMER_LAG", "LATENCY_SLO", "ERROR_BUDGET_EXHAUSTED"},
        "hot-partition": {"HOT_PARTITION", "ERROR_BUDGET_EXHAUSTED"},
        "rebalance-storm": {"REBALANCE_STORM", "LATENCY_SLO"},
        "broker-failure": {"OFFLINE_PARTITIONS", "UNDER_REPLICATED_PARTITIONS", "CONSUMER_LAG", "DISK_PRESSURE"},
        "schema-break": {"SCHEMA_INCOMPATIBILITY", "POISON_MESSAGES"},
        "duplicate-processing": {"DUPLICATE_PROCESSING"},
        "poison-message": {"POISON_MESSAGES"},
    }
    for scenario, subset in expected.items():
        response = client.post(f"/v1/scenarios/{scenario}")
        assert response.status_code == 200
        codes = {finding["code"] for finding in response.json()["findings"]}
        assert subset <= codes


def test_hot_partition_uses_distribution_not_aggregate_only() -> None:
    result = diagnose(StreamingSnapshot(
        produced_total=10_000, consumed_total=10_000, consumer_lag=5_000,
        partition_lag={"0": 4_800, "1": 100, "2": 100},
    ))
    finding = next(item for item in result.findings if item.code == "HOT_PARTITION")
    assert finding.evidence["partition"] == "0"


def test_error_budget_math() -> None:
    slo = assess_slo(StreamingSnapshot(produced_total=100_000, consumed_total=99_800, consumer_lag=200))
    assert slo.availability == 0.998
    assert slo.burn_rate == 2.0
    assert slo.status == "exhausted"


def test_crca_does_not_invent_root_cause() -> None:
    assessment = diagnose(StreamingSnapshot(
        produced_total=100, consumed_total=80, consumer_lag=20_000, offline_partitions=1,
    ))
    document = render_crca(assessment)
    assert "Not yet established" in document
    assert "must not present correlation as causation" in document
    assert "Human technical review" in document


def test_aria_contract_is_explicitly_non_autonomous() -> None:
    response = client.post("/v1/scenarios/broker-failure")
    incident_id = response.json()["incident_id"]
    assert incident_id in RECENT
    evidence = client.get(f"/v1/incidents/{incident_id}/aria-evidence?tenant=banking").json()
    assert evidence["source"] == "aria"
    assert evidence["schema_version"] == "1.0"
    assert evidence["tenant"] == "banking"
    assert evidence["automatic_remediation"] is False
