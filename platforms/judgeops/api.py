from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field

from packages.contracts import ModelEndpoint
from packages.security.auth import AuthorizationError, Identity, require_roles
from packages.security.fastapi_auth import current_identity
from platforms.agents.providers import OpenAICompatibleModel, UrllibTransport

from .calibration import CalibrationCase, CalibrationPolicy, calibrate
from .contracts import JudgeSample, Verdict
from .ensemble import EnsembleJudge
from .providers import DeterministicJudge, OpenAIJudge
from .rubrics import RUBRICS
from .store import JudgeStore

app = FastAPI(title="OpenModelOps JudgeOps", version="0.1.0")
app.state.store = JudgeStore(os.getenv("JUDGEOPS_DATABASE", ":memory:"))
IdentityDependency = Annotated[Identity, Depends(current_identity)]
REQUESTS = Counter("openmodelops_judge_requests_total", "Judge requests", ["verdict", "rubric"])
LATENCY = Histogram("openmodelops_judge_duration_seconds", "Judge evaluation latency", ["rubric"])


def _judges():
    provider = os.getenv("JUDGE_PROVIDER", "deterministic")
    if provider == "deterministic":
        return [DeterministicJudge()]
    if provider == "openai-compatible":
        model_id = os.getenv("JUDGE_MODEL_ID", "mlx-community/Qwen3-0.6B-4bit")
        endpoint = ModelEndpoint(
            "judge-model",
            model_id,
            os.getenv("JUDGE_MODEL_BASE_URL", "http://127.0.0.1:8008"),
            timeout_seconds=int(os.getenv("JUDGE_TIMEOUT_SECONDS", "120")),
        )
        return [
            OpenAIJudge(
                OpenAICompatibleModel(UrllibTransport(), os.getenv("JUDGE_MODEL_API_KEY", "")),
                endpoint,
                "primary-judge",
                model_id,
            )
        ]
    raise RuntimeError("JUDGE_PROVIDER must be deterministic or openai-compatible")


class EvaluationRequest(BaseModel):
    rubric_id: str
    sample: JudgeSample


class CalibrationItem(BaseModel):
    case_id: str
    human_pass: bool
    judge_verdict: Verdict
    pass_probability: float | None = Field(default=None, ge=0, le=1)


class CalibrationRequest(BaseModel):
    cases: list[CalibrationItem] = Field(min_length=2, max_length=100_000)


class ResolveReviewRequest(BaseModel):
    verdict: Verdict
    reason: str = Field(min_length=3, max_length=5000)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    _judges()
    return {"status": "ready", "provider": os.getenv("JUDGE_PROVIDER", "deterministic")}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/rubrics")
def rubrics() -> dict:
    return {"rubrics": [rubric.model_dump() | {"digest": rubric.digest} for rubric in RUBRICS.values()]}


@app.post("/v1/evaluations")
def evaluate(request: EvaluationRequest) -> dict:
    rubric = RUBRICS.get(request.rubric_id)
    if rubric is None:
        raise HTTPException(status_code=404, detail="rubric not found")
    try:
        with LATENCY.labels(rubric.rubric_id).time():
            result = EnsembleJudge(_judges()).evaluate(request.sample, rubric)
    except (RuntimeError, ValueError) as exc:
        REQUESTS.labels("error", rubric.rubric_id).inc()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    REQUESTS.labels(result.verdict.value, rubric.rubric_id).inc()
    evaluation_id = app.state.store.record(
        result, queue_review=result.verdict == Verdict.REVIEW or request.sample.risk_tier in {"high", "critical"}
    )
    return {
        "evaluation_id": evaluation_id,
        "sample_id": result.sample_id,
        "verdict": result.verdict,
        "scores": result.scores,
        "weighted_score": result.weighted_score,
        "confidence": result.confidence,
        "maximum_disagreement": result.maximum_disagreement,
        "reason": result.reason,
        "judges": [item.model_dump() for item in result.judge_results],
    }


@app.post("/v1/calibration")
def calibration(request: CalibrationRequest) -> dict:
    try:
        report = calibrate(
            [
                CalibrationCase(item.case_id, item.human_pass, item.judge_verdict, item.pass_probability)
                for item in request.cases
            ]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.__dict__


@app.post("/v1/calibration/qualify")
def qualify_calibration(request: CalibrationRequest) -> dict:
    try:
        report = calibrate(
            [
                CalibrationCase(item.case_id, item.human_pass, item.judge_verdict, item.pass_probability)
                for item in request.cases
            ]
        )
        CalibrationPolicy().qualify(report)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"qualified": True, "report": report.__dict__}


@app.get("/v1/reviews")
def pending_reviews(limit: int = 100) -> dict:
    if not 1 <= limit <= 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    return {"reviews": app.state.store.pending_reviews(limit)}


@app.post("/v1/reviews/{evaluation_id}/resolve")
def resolve_review(
    evaluation_id: str,
    request: ResolveReviewRequest,
    identity: IdentityDependency,
) -> dict:
    try:
        require_roles("judge-reviewer")(identity)
        return app.state.store.resolve(evaluation_id, identity.subject, request.verdict, request.reason)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail="judge-reviewer role required") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
