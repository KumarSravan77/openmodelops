from __future__ import annotations

import base64
import json
import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from packages.security.auth import AuthorizationError, Identity, require_roles
from packages.security.fastapi_auth import current_identity
from platforms.factory.catalog import Catalog
from platforms.factory.domain import SLO, FactorySpec, FactoryWorkload, GateResult, GateStatus, WorkloadKind
from platforms.factory.governance import EvidenceStatement, EvidenceVerifier, FactoryPolicy
from platforms.factory.store import ConcurrencyError, FactoryStore
from platforms.integrations.aria_intelligence import (
    AriaIntelligenceStore,
    AriaIntelligenceVerifier,
    IntelligenceVerificationError,
)

app = FastAPI(title="OpenModelOps AI SRE Factory", version="0.1.0")
CATALOG_PATH = Path(__file__).resolve().parents[2] / "catalog" / "components"
IdentityDependency = Annotated[Identity, Depends(current_identity)]


class SLORequest(BaseModel):
    availability_target: float
    latency_p95_ms: int
    error_rate_target: float


class WorkloadRequest(BaseModel):
    name: str
    kind: WorkloadKind
    owner: str
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
    evidence_digest: str
    signing_key_id: str = ""
    signature: str = ""


class ActionRequest(BaseModel):
    reason: str = ""


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    try:
        if factory_store().ready():
            return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="factory database unavailable") from exc
    raise HTTPException(status_code=503, detail="factory database unavailable")


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


@lru_cache
def factory_store() -> FactoryStore:
    return FactoryStore(os.getenv("FACTORY_DATABASE_URL", "sqlite:///./openmodelops-factory.db"))


@app.post("/api/v1/intelligence/aria")
async def receive_aria_intelligence(
    request: Request,
    timestamp: str = Header(alias="X-ARIA-Timestamp"),
    nonce: str = Header(alias="X-ARIA-Nonce"),
    signature: str = Header(alias="X-ARIA-Signature"),
) -> dict[str, str]:
    body = await request.body()
    try:
        payload = AriaIntelligenceVerifier(os.getenv("ARIA_INTEGRATION_SECRET", "")).verify(
            body, timestamp, nonce, signature
        )
        AriaIntelligenceStore(factory_store().engine).record(payload, nonce, datetime.now(UTC).isoformat())
    except IntelligenceVerificationError as exc:
        raise HTTPException(status_code=401 if "signature" in str(exc) else 409, detail=str(exc)) from exc
    return {"signal_id": payload["signal_id"], "status": "accepted"}


@app.get("/workloads/{workload_id}/incident-scorecard")
def incident_scorecard(workload_id: str, identity: IdentityDependency) -> dict:
    authorize(identity, "factory-admin")
    get_workload(workload_id, identity.tenant)
    return AriaIntelligenceStore(factory_store().engine).scorecard(identity.tenant, workload_id)


def authorize(identity: Identity, role: str) -> None:
    try:
        require_roles(role)(identity)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail="required role missing") from exc


def verify_gate_evidence(statement: EvidenceStatement, request: GateRequest) -> None:
    raw_keys = json.loads(os.getenv("EVIDENCE_PUBLIC_KEYS_JSON", "{}"))
    public_keys = {key_id: base64.b64decode(value) for key_id, value in raw_keys.items()}
    production = os.getenv("FACTORY_ENV", "development") == "production"
    if production and (not request.signing_key_id or not request.signature):
        raise HTTPException(status_code=422, detail="signed evidence is required in production")
    if request.signing_key_id or request.signature:
        try:
            EvidenceVerifier(public_keys).verify(statement, request.signing_key_id, request.signature)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/components")
def components() -> list[dict[str, object]]:
    return component_catalog().summary()


@app.post("/workloads")
def create_workload(request: WorkloadRequest, identity: IdentityDependency) -> dict:
    authorize(identity, "factory-admin")
    try:
        values = request.model_dump(exclude={"slo"})
        workload = FactoryWorkload(FactorySpec(**values, tenant=identity.tenant, slo=SLO(**request.slo.model_dump())))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    version = factory_store().create(workload)
    return view(workload, version)


@app.put("/workloads/{workload_id}/gates")
def record_gate(workload_id: str, request: GateRequest, identity: IdentityDependency) -> dict:
    authorize(identity, "gate-evaluator")
    workload, version = get_workload(workload_id, identity.tenant)
    statement = EvidenceStatement(
        workload_id=workload_id,
        gate=request.gate,
        evidence_uri=request.evidence,
        evidence_digest=request.evidence_digest,
        evaluator=identity.subject,
    )
    verify_gate_evidence(statement, request)
    try:
        workload.record_gate(
            GateResult(
                gate=request.gate,
                status=GateStatus.PASS if request.passed else GateStatus.FAIL,
                evidence=request.evidence,
                evaluator=identity.subject,
                evidence_digest=request.evidence_digest,
                signing_key_id=request.signing_key_id,
                signature=request.signature,
            )
        )
        version = factory_store().save(workload, version)
    except ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return view(workload, version)


@app.post("/workloads/{workload_id}/{operation}")
def advance(
    workload_id: str,
    operation: str,
    request: ActionRequest,
    identity: IdentityDependency,
) -> dict:
    authorize(identity, "release-approver" if operation == "approve" else "factory-admin")
    workload, version = get_workload(workload_id, identity.tenant)
    try:
        if operation == "approve":
            decision = FactoryPolicy().evaluate(workload.spec)
            if not decision.allowed:
                raise ValueError(f"policy denied release: {list(decision.reasons)}")
            workload.approve(identity.subject, decision.policy_digest)
        elif operation == "provision":
            workload.provision(identity.subject)
        elif operation == "release":
            workload.release(identity.subject)
        elif operation == "suspend":
            workload.suspend(identity.subject, request.reason)
        elif operation == "retire":
            workload.retire(identity.subject, request.reason)
        else:
            raise HTTPException(status_code=404, detail="unknown operation")
        version = factory_store().save(workload, version)
    except ConcurrencyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return view(workload, version)


def get_workload(workload_id: str, tenant: str) -> tuple[FactoryWorkload, int]:
    result = factory_store().get(workload_id, tenant)
    if result is None:
        raise HTTPException(status_code=404, detail="workload not found")
    return result


def view(workload: FactoryWorkload, version: int = 0) -> dict:
    return {
        "workload_id": workload.workload_id,
        "name": workload.spec.name,
        "kind": workload.spec.kind.value,
        "stage": workload.stage.value,
        "scorecard": workload.scorecard(),
        "approved_by": workload.approved_by,
        "policy_digest": workload.policy_digest,
        "history": workload.history,
        "version": version,
    }
