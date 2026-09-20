from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from packages.observability.telemetry import telemetry_from_environment
from packages.security.auth import Identity
from packages.security.fastapi_auth import current_identity
from platforms.kubernetes_sre.actions import ActionProposal, ActionType, ChangeExecutor, SafetyViolation
from platforms.kubernetes_sre.analyzers import ParallelAnalyzer
from platforms.kubernetes_sre.client import OfficialKubernetesClient
from platforms.kubernetes_sre.service import KubernetesSREService
from platforms.kubernetes_sre.store import SREStore

logger = logging.getLogger(__name__)


async def scheduled_inspection() -> None:
    interval = max(30, int(os.getenv("KUBERNETES_SRE_INSPECTION_INTERVAL_SECONDS", "300")))
    cluster = os.getenv("KUBERNETES_SRE_CLUSTER", "in-cluster")
    while True:
        try:
            await asyncio.to_thread(service().inspect, cluster)
        except Exception:
            logger.exception("scheduled Kubernetes inspection failed", extra={"cluster": cluster})
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if os.getenv("KUBERNETES_SRE_SCHEDULER_ENABLED", "true").lower() == "true":
        task = asyncio.create_task(scheduled_inspection())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="OpenModelOps Kubernetes SRE Agent", version="0.1.0", lifespan=lifespan)
AuthenticatedIdentity = Annotated[Identity, Depends(current_identity)]


def require_role(identity: Identity, role: str) -> None:
    if role not in identity.roles:
        raise HTTPException(status_code=403, detail=f"{role} role required")


@lru_cache
def service() -> KubernetesSREService:
    client = OfficialKubernetesClient()
    store = SREStore(os.getenv("KUBERNETES_SRE_DB", "/data/kubernetes-sre.db"))
    namespaces = frozenset(filter(None, os.getenv("KUBERNETES_SRE_MANAGED_NAMESPACES", "openmodelops-managed").split(",")))
    execution_enabled = os.getenv("KUBERNETES_SRE_EXECUTION_ENABLED", "false").lower() == "true"
    executor = ChangeExecutor(client, namespaces) if execution_enabled else None
    return KubernetesSREService(
        client, ParallelAnalyzer(), store, executor, telemetry_from_environment("openmodelops-kubernetes-sre")
    )


class ProposalRequest(BaseModel):
    action: ActionType
    cluster: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    resource_name: str = Field(min_length=1)
    resource_uid: str = Field(min_length=1)
    resource_version: str = Field(min_length=1)
    rationale: str = Field(min_length=10)
    rollback: str = Field(min_length=10)
    parameters: dict[str, int | str] = Field(default_factory=dict)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    try:
        service()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="dependencies are not ready") from exc


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/clusters/{cluster}/inspect")
def inspect(cluster: str, identity: AuthenticatedIdentity) -> dict[str, object]:
    require_role(identity, "sre-reader")
    try:
        return service().inspect(cluster).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="cluster inspection failed") from exc


@app.post("/v1/proposals")
def propose(request: ProposalRequest, identity: AuthenticatedIdentity) -> dict[str, str]:
    require_role(identity, "sre-proposer")
    proposal = ActionProposal(**request.model_dump(), requested_by=identity.subject)
    service().propose(proposal)
    return {"proposal_id": proposal.proposal_id, "digest": proposal.digest, "status": "proposed"}


@app.post("/v1/proposals/{proposal_id}/approve")
def approve(proposal_id: str, identity: AuthenticatedIdentity) -> dict[str, str]:
    require_role(identity, "sre-approver")
    try:
        approval = service().approve(proposal_id, identity.subject)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"proposal_id": proposal_id, "approved_by": approval.approved_by, "status": "approved"}


@app.post("/v1/proposals/{proposal_id}/execute")
def execute(proposal_id: str, identity: AuthenticatedIdentity) -> dict[str, str]:
    require_role(identity, "sre-executor")
    try:
        result = service().execute(proposal_id, identity.subject)
    except (KeyError, ValueError, RuntimeError, SafetyViolation) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"proposal_id": proposal_id, "resource_version": result, "status": "executed"}
