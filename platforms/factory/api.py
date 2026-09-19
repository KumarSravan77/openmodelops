from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from platforms.factory.catalog import Catalog
from platforms.factory.domain import SLO, FactorySpec, FactoryWorkload, GateResult, GateStatus, WorkloadKind

app = FastAPI(title="OpenModelOps AI SRE Factory", version="0.1.0")
workloads: dict[str, FactoryWorkload] = {}
CATALOG_PATH = Path(__file__).resolve().parents[2] / "catalog" / "components"


class SLORequest(BaseModel):
    availability_target: float
    latency_p95_ms: int
    error_rate_target: float


class WorkloadRequest(BaseModel):
    name: str
    kind: WorkloadKind
    owner: str
    tenant: str
    environment: str
    artifact_digest: str
    data_classification: str
    slo: SLORequest
    requires_gpu: bool = False
    internet_egress: bool = False


class GateRequest(BaseModel):
    gate: str
    passed: bool
    evidence: str
    evaluator: str


class ActionRequest(BaseModel):
    actor: str
    reason: str = ""


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/capabilities")
def capabilities() -> dict[str, list[str]]:
    return {
        "mlops": ["training", "evaluation", "registry", "release-gates", "feature-contracts"],
        "llmops": ["open-weight-catalog", "ollama", "vllm", "evaluation", "routing"],
        "agentops": ["guardrails", "bounded-tools", "tracing", "feedback", "release-governance"],
        "ai_sre": ["slos", "scorecards", "observability", "incident-workflow", "verified-remediation"],
    }


@lru_cache
def component_catalog() -> Catalog:
    return Catalog.load(CATALOG_PATH)


@app.get("/components")
def components() -> list[dict[str, object]]:
    return component_catalog().summary()


@app.post("/workloads")
def create_workload(request: WorkloadRequest) -> dict:
    try:
        values = request.model_dump(exclude={"slo"})
        workload = FactoryWorkload(FactorySpec(**values, slo=SLO(**request.slo.model_dump())))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    workloads[workload.workload_id] = workload
    return view(workload)


@app.put("/workloads/{workload_id}/gates")
def record_gate(workload_id: str, request: GateRequest) -> dict:
    workload = get_workload(workload_id)
    try:
        workload.record_gate(
            GateResult(
                gate=request.gate,
                status=GateStatus.PASS if request.passed else GateStatus.FAIL,
                evidence=request.evidence,
                evaluator=request.evaluator,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return view(workload)


@app.post("/workloads/{workload_id}/{operation}")
def advance(workload_id: str, operation: str, request: ActionRequest) -> dict:
    workload = get_workload(workload_id)
    try:
        if operation == "approve":
            workload.approve(request.actor)
        elif operation == "provision":
            workload.provision(request.actor)
        elif operation == "release":
            workload.release(request.actor)
        elif operation == "suspend":
            workload.suspend(request.actor, request.reason)
        elif operation == "retire":
            workload.retire(request.actor, request.reason)
        else:
            raise HTTPException(status_code=404, detail="unknown operation")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return view(workload)


def get_workload(workload_id: str) -> FactoryWorkload:
    workload = workloads.get(workload_id)
    if workload is None:
        raise HTTPException(status_code=404, detail="workload not found")
    return workload


def view(workload: FactoryWorkload) -> dict:
    return {
        "workload_id": workload.workload_id,
        "name": workload.spec.name,
        "kind": workload.spec.kind.value,
        "stage": workload.stage.value,
        "scorecard": workload.scorecard(),
        "approved_by": workload.approved_by,
        "history": workload.history,
    }
