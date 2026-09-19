from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from pydantic import BaseModel, Field

from .domain import EvaluationPolicy, ModelRun, RunState
from .store import RunStore

app = FastAPI(title="OpenModelOps MLOps Control Plane", version="0.1.0")
store = RunStore(os.environ.get("MLOPS_DB_PATH", "openmodelops-mlops.db"))
transitions = Counter("openmodelops_mlops_transitions_total", "Model lifecycle transitions", ["target"])


class CreateRun(BaseModel):
    model_name: str = Field(min_length=1, max_length=120)
    dataset_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    code_revision: str = Field(min_length=7, max_length=80)
    owner: str = Field(min_length=1, max_length=120)


class Transition(BaseModel):
    target: RunState
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=1000)


class Evaluation(BaseModel):
    metrics: dict[str, float]
    artifact_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    actor: str
    minimum_metrics: dict[str, float]
    maximum_metrics: dict[str, float] = {}


def _serialize(run: ModelRun, revision: int) -> dict[str, Any]:
    return {**run.__dict__, "state": run.state.value, "revision": revision}


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    store._init()
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/runs", status_code=201)
def create_run(request: CreateRun) -> dict[str, Any]:
    run = ModelRun(run_id=str(uuid.uuid4()), **request.model_dump())
    return _serialize(run, store.save(run))


@app.get("/v1/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    try:
        return _serialize(*store.get(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.post("/v1/runs/{run_id}/transition")
def transition_run(run_id: str, request: Transition, if_match: int = Header(alias="If-Match")) -> dict[str, Any]:
    try:
        run, revision = store.get(run_id)
        if revision != if_match:
            raise HTTPException(status_code=409, detail="stale revision")
        run.transition(request.target, request.actor, request.reason)
        transitions.labels(request.target.value).inc()
        return _serialize(run, store.save(run, revision))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/runs/{run_id}/evaluation")
def record_evaluation(run_id: str, request: Evaluation, if_match: int = Header(alias="If-Match")) -> dict[str, Any]:
    try:
        run, revision = store.get(run_id)
        if revision != if_match:
            raise HTTPException(status_code=409, detail="stale revision")
        run.record_evaluation(
            request.metrics,
            request.artifact_digest,
            EvaluationPolicy(request.minimum_metrics, request.maximum_metrics),
            request.actor,
        )
        return _serialize(run, store.save(run, revision))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
