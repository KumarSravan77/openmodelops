from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

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


def scenario_data() -> dict[str, dict]:
    return json.loads(SCENARIO_PATH.read_text())


def record(snapshot: StreamingSnapshot) -> StreamingAssessment:
    assessment = diagnose(snapshot)
    RECENT[assessment.incident_id] = assessment
    ASSESSMENTS.labels(assessment.severity.value).inc()
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
