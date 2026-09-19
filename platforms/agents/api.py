from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

from packages.contracts import ModelEndpoint
from packages.observability import telemetry_from_environment

from .feedback import Feedback, FeedbackStore
from .policy import GuardrailUnavailable, LocalGuardrail, ToolRegistry
from .providers import OllamaModel, OpenAICompatibleModel, UrllibTransport
from .runtime import AgentRelease, AgentRuntime, EchoModel

app = FastAPI(title="OpenModelOps Agent Platform", version="0.1.0")
provider = os.environ.get("MODEL_PROVIDER", "echo")
model_client = {
    "echo": EchoModel(),
    "ollama": OllamaModel(UrllibTransport()),
    "vllm": OpenAICompatibleModel(UrllibTransport(), os.environ.get("MODEL_API_KEY", "")),
}.get(provider)
if model_client is None:
    raise RuntimeError("MODEL_PROVIDER must be echo, ollama or vllm")
runtime = AgentRuntime(model_client, LocalGuardrail(), ToolRegistry(), telemetry_from_environment("openmodelops-agents"))
feedback = FeedbackStore()
requests_total = Counter("openmodelops_agent_requests_total", "Agent requests", ["status", "agent"])
latency = Histogram("openmodelops_agent_request_duration_seconds", "Agent request latency", ["agent"])

release = AgentRelease(
    name="operations-assistant",
    revision="prompt-v1",
    prompt="Answer from authorized context. Never invent actions, credentials or incident facts.",
    model=ModelEndpoint(
        "open-weight-model",
        os.environ.get("MODEL_ID", "qwen2.5:3b"),
        os.environ.get("MODEL_BASE_URL", "http://ollama:11434"),
    ),
)


class Invocation(BaseModel):
    input: str = Field(min_length=1, max_length=20_000)


class FeedbackRequest(BaseModel):
    trace_id: str
    score: int
    category: str
    comment: str = Field(default="", max_length=2000)


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    if runtime.guardrail is None:
        raise HTTPException(status_code=503, detail="guardrail unavailable")
    return {"status": "ready"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/agents/{agent_name}/invoke")
def invoke(agent_name: str, request: Invocation) -> dict:
    if agent_name != release.name:
        raise HTTPException(status_code=404, detail="agent release not found")
    try:
        with latency.labels(agent_name).time():
            result = runtime.invoke(release, request.input)
        requests_total.labels(result["status"], agent_name).inc()
        return result
    except GuardrailUnavailable as exc:
        requests_total.labels("guardrail_unavailable", agent_name).inc()
        raise HTTPException(status_code=503, detail="safety dependency unavailable") from exc


@app.post("/v1/feedback", status_code=202)
def submit_feedback(request: FeedbackRequest) -> dict[str, str]:
    try:
        feedback.add(Feedback(**request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "queued_for_curation"}
