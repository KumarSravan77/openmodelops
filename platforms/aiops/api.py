from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from platforms.aiops.workflow import Incident, Remediation, Signal

app = FastAPI(title="OpenModelOps AIOps Control Plane", version="0.1.0")
incidents: dict[str, Incident] = {}


class SignalRequest(BaseModel):
    source: str
    service: str
    severity: str
    fingerprint: str
    observed_at: datetime
    attributes: dict[str, str] = {}


class IncidentRequest(BaseModel):
    service: str
    signals: list[SignalRequest]


class ActionRequest(BaseModel):
    actor: str
    action: str | None = None
    target: str | None = None
    rationale: str | None = None
    risk: str | None = None
    rollback: str | None = None
    healthy: bool | None = None


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/incidents")
def create_incident(request: IncidentRequest) -> dict:
    incident = Incident(
        service=request.service,
        signals=[Signal(**signal.model_dump()) for signal in request.signals],
    )
    incidents[incident.incident_id] = incident
    return view(incident)


@app.post("/incidents/{incident_id}/{operation}")
def advance(incident_id: str, operation: str, request: ActionRequest) -> dict:
    incident = incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    try:
        if operation == "correlate":
            incident.correlate(request.actor)
        elif operation == "investigate":
            incident.investigate(request.actor)
        elif operation == "recommend":
            incident.recommend(
                Remediation(
                    action=request.action or "",
                    target=request.target or "",
                    rationale=request.rationale or "",
                    risk=request.risk or "",
                    rollback=request.rollback or "",
                ),
                request.actor,
            )
        elif operation == "approve":
            incident.approve(request.actor)
        elif operation == "execute":
            incident.execute(request.actor)
        elif operation == "verify":
            incident.verify(bool(request.healthy), request.actor)
        else:
            raise HTTPException(status_code=404, detail="unknown operation")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return view(incident)


def view(incident: Incident) -> dict:
    return {
        "incident_id": incident.incident_id,
        "service": incident.service,
        "state": incident.state.value,
        "approved_by": incident.approved_by,
        "audit": incident.audit,
    }
