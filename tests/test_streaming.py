from fastapi.testclient import TestClient

from platforms.streaming.api import RECENT, FireDrillEnvelope, app, evaluate_fire_drill
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
    slo = assess_slo(StreamingSnapshot(
        produced_total=100_000, consumed_total=99_800, consumer_lag=200,
        eligible_events_total=100_000, completed_within_objective_total=99_800,
    ))
    assert slo.completion_ratio == 0.998
    assert slo.burn_rate == 2.0
    assert slo.status == "exhausted"


def test_raw_producer_consumer_counts_are_not_treated_as_slo() -> None:
    slo = assess_slo(StreamingSnapshot(produced_total=100_000, consumed_total=80_000, consumer_lag=20_000))
    assert slo.status == "insufficient-data"
    assert slo.burn_rate is None


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


def test_fire_drill_bridge_preserves_chain_of_custody() -> None:
    envelope = FireDrillEnvelope.model_validate({
        "schema_version": "1.0", "source": "fire-drill", "evidence_mode": "synthetic", "event_id": "event-1",
        "experiment_id": "drill-1", "service": "payment-events", "environment": "staging",
        "scenario": "network-latency", "phase": "observed", "observed_at": "2026-09-21T00:00:00Z",
        "plan_digest": "sha256:" + "a" * 64, "approved_by": "reliability-reviewer",
        "blast_radius_percent": 10, "stop_conditions": ["lag above 10000"],
        "report_card": {"detection": "PASS", "recovery": "PASS", "verdict": "ACTION_REQUIRED",
                        "detection_seconds": 12, "recovery_seconds": 45},
        "snapshot": {"cluster": "local-redpanda", "workload_id": "payment-stream",
                     "topic": "payments", "consumer_group": "fraud-detector",
                     "produced_total": 100000, "consumed_total": 80000, "consumer_lag": 20000,
                     "partition_lag": {"0": 18000, "1": 1000, "2": 1000}},
    })
    result = evaluate_fire_drill(envelope)
    assert result["experiment_id"] == "drill-1"
    assert result["plan_digest"] == "sha256:" + "a" * 64
    aria = result["aria_request"]
    assert aria["context"]["automatic_remediation"] is False
    assert aria["context"]["fire_drill_report"]["detection_seconds"] == 12
    assert aria["context"]["qualification_verdict"] == "ACTION_REQUIRED"
    assert "CONSUMER_LAG" in aria["incident"]["signals"]
