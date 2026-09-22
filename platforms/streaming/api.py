from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel, Field

from platforms.streaming.reliability import StreamingAssessment, StreamingSnapshot, diagnose, render_crca

app = FastAPI(title="OpenModelOps Streaming Reliability", version="0.1.0")

ASSESSMENTS = Counter("streaming_assessments_total", "Streaming reliability assessments", ["severity"])
FINDINGS = Counter("streaming_findings_total", "Streaming reliability findings", ["code"])
ERROR_BUDGET_BURN = Gauge("streaming_error_budget_burn_rate", "Current streaming error-budget burn rate", ["cluster"])
CONSUMER_LAG = Gauge("streaming_consumer_lag", "Current aggregate consumer lag", ["cluster"])

SCENARIO_PATH = Path(
    os.getenv(
        "STREAMING_SCENARIOS",
        Path(__file__).resolve().parents[2] / "examples" / "streaming-reliability" / "scenarios.json",
    )
)
RECENT: dict[str, StreamingAssessment] = {}


class FireDrillEnvelope(BaseModel):
    schema_version: Literal["1.0"]
    source: Literal["fire-drill"]
    evidence_mode: Literal["synthetic"]
    event_id: str
    experiment_id: str
    service: str
    environment: Literal["development", "staging"]
    scenario: str
    phase: Literal["observed"]
    observed_at: str
    plan_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    approved_by: str | None = None
    blast_radius_percent: int = Field(ge=1, le=25)
    stop_conditions: list[str] = Field(min_length=1)
    report_card: dict[str, object]
    snapshot: StreamingSnapshot


def evaluate_fire_drill(envelope: FireDrillEnvelope) -> dict[str, object]:
    if envelope.schema_version != "1.0" or envelope.source != "fire-drill" or envelope.phase != "observed":
        raise ValueError("unsupported Fire Drill evidence contract")
    assessment = record(envelope.snapshot)
    severity = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4", "info": "P4"}[
        assessment.severity.value
    ]
    codes = [finding.code for finding in assessment.findings]
    qualification_verdict = (
        "ACTION_REQUIRED"
        if envelope.report_card.get("verdict") != "PASS" or assessment.slo.status != "healthy"
        else "PASS"
    )
    return {
        "schema_version": "1.0",
        "source": "openmodelops",
        "evidence_mode": envelope.evidence_mode,
        "experiment_id": envelope.experiment_id,
        "event_id": envelope.event_id,
        "plan_digest": envelope.plan_digest,
        "fire_drill_report": envelope.report_card,
        "qualification_verdict": qualification_verdict,
        "assessment": assessment.model_dump(mode="json"),
        "aria_request": {
            "incident": {
                "incident_id": assessment.incident_id,
                "service": envelope.service,
                "severity": severity,
                "source": "fire-drill",
                "signals": ["kafka", "streaming", *codes],
                "topic": envelope.snapshot.topic,
                "consumer_group": envelope.snapshot.consumer_group,
            },
            "context": {
                "experiment_id": envelope.experiment_id,
                "event_id": envelope.event_id,
                "plan_digest": envelope.plan_digest,
                "evidence_digest": assessment.evidence_digest,
                "scenario": envelope.scenario,
                "evidence_mode": envelope.evidence_mode,
                "environment": envelope.environment,
                "approved_by": envelope.approved_by,
                "blast_radius_percent": envelope.blast_radius_percent,
                "automatic_remediation": False,
                "streaming_observation": envelope.snapshot.model_dump(mode="json"),
                "findings": [finding.model_dump(mode="json") for finding in assessment.findings],
                "slo": assessment.slo.model_dump(mode="json"),
                "fire_drill_report": envelope.report_card,
                "qualification_verdict": qualification_verdict,
            },
        },
    }


def scenario_data() -> dict[str, dict]:
    return json.loads(SCENARIO_PATH.read_text())


def record(snapshot: StreamingSnapshot) -> StreamingAssessment:
    assessment = diagnose(snapshot)
    RECENT[assessment.incident_id] = assessment
    ASSESSMENTS.labels(assessment.severity.value).inc()
    if assessment.slo.burn_rate is not None:
        ERROR_BUDGET_BURN.labels(snapshot.cluster).set(assessment.slo.burn_rate)
    CONSUMER_LAG.labels(snapshot.cluster).set(snapshot.consumer_lag)
    for finding in assessment.findings:
        FINDINGS.labels(finding.code).inc()
    return assessment


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    if SCENARIO_PATH.is_file():
        return {"status": "ready"}
    raise HTTPException(status_code=503, detail="scenario catalog unavailable")


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/scenarios")
def scenarios() -> dict[str, list[str]]:
    return {"scenarios": sorted(scenario_data())}


@app.post("/v1/scenarios/{name}", response_model=StreamingAssessment)
def run_scenario(name: str) -> StreamingAssessment:
    scenario = scenario_data().get(name)
    if scenario is None:
        raise HTTPException(status_code=404, detail="unknown scenario")
    return record(StreamingSnapshot(**scenario))


@app.post("/v1/assess", response_model=StreamingAssessment)
def assess(snapshot: StreamingSnapshot) -> StreamingAssessment:
    return record(snapshot)


@app.post("/v1/fire-drills/evaluate")
def fire_drill_evaluate(envelope: FireDrillEnvelope) -> dict[str, object]:
    try:
        return evaluate_fire_drill(envelope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/incidents/{incident_id}/aria-evidence")
def aria_evidence(incident_id: str, tenant: str = "local") -> dict[str, object]:
    assessment = RECENT.get(incident_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return assessment.aria_evidence(tenant)


@app.get("/v1/incidents/{incident_id}/crca")
def crca(incident_id: str) -> Response:
    assessment = RECENT.get(incident_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return Response(render_crca(assessment), media_type="text/markdown")
