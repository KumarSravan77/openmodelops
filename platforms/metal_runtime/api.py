from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field

from .backend import DevelopmentBackend, InferenceBackend, MLXBackend, estimate_tokens
from .cache import PromptCacheIndex
from .hardware import HardwareProfile, detect_hardware
from .planner import AdmissionRequest, MemoryPlanner, ModelProfile
from .scheduler import BoundedScheduler

REQUESTS = Counter("openmodelops_metal_requests_total", "Metal runtime requests", ["status", "cache"])
LATENCY = Histogram("openmodelops_metal_request_duration_seconds", "Metal runtime request latency")
ACTIVE = Gauge("openmodelops_metal_active_requests", "Active Metal inference requests")
QUEUED = Gauge("openmodelops_metal_queued_requests", "Queued Metal inference requests")
CLAMPED = Counter("openmodelops_metal_context_clamped_total", "Requests with generation capacity clamped")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=2_000_000)


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    max_tokens: int = Field(default=1024, ge=1, le=16384)
    stream: bool = False
    multimodal: bool = False


class PlanRequest(BaseModel):
    prompt_tokens: int = Field(ge=1)
    max_tokens: int = Field(default=1024, ge=1, le=16384)
    active_slots: int = Field(default=0, ge=0)
    multimodal: bool = False


def _prompt(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{message.role}: {message.content}" for message in messages)


def _model_profile() -> ModelProfile:
    return ModelProfile(
        model_id=os.getenv("METAL_MODEL_ID", "mlx-community/Qwen3-8B-4bit"),
        parameter_billions=float(os.getenv("METAL_MODEL_PARAMETERS_B", "8")),
        weight_bits=int(os.getenv("METAL_MODEL_WEIGHT_BITS", "4")),
        kv_bytes_per_token_fp16=int(os.getenv("METAL_KV_BYTES_PER_TOKEN_FP16", "65536")),
        kv_bits=int(os.getenv("METAL_KV_BITS", "8")),
    )


def _backend(model_id: str) -> InferenceBackend:
    name = os.getenv("METAL_BACKEND", "development")
    if name == "development":
        return DevelopmentBackend()
    if name == "mlx":
        return MLXBackend(model_id)
    raise RuntimeError("METAL_BACKEND must be development or mlx")


def create_app(
    hardware: HardwareProfile | None = None,
    model: ModelProfile | None = None,
    backend: InferenceBackend | None = None,
) -> FastAPI:
    detected = hardware or detect_hardware()
    selected_model = model or _model_profile()
    slots = int(os.getenv("METAL_MAXIMUM_SLOTS", "2"))
    scheduler = BoundedScheduler(backend or _backend(selected_model.model_id), slots, int(os.getenv("METAL_QUEUE_LIMIT", "20")))
    planner = MemoryPlanner(
        detected.memory_gb,
        selected_model,
        system_reserve_gb=float(os.getenv("METAL_SYSTEM_RESERVE_GB", "6")),
        runtime_reserve_gb=float(os.getenv("METAL_RUNTIME_RESERVE_GB", "2")),
        maximum_slots=slots,
    )
    cache = PromptCacheIndex(int(os.getenv("METAL_PROMPT_CACHE_ENTRIES", "128")))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await scheduler.start()
        yield
        await scheduler.stop()

    application = FastAPI(title="OpenModelOps Metal Runtime", version="0.1.0", lifespan=lifespan)
    application.state.hardware = detected
    application.state.model = selected_model
    application.state.planner = planner
    application.state.scheduler = scheduler
    application.state.cache = cache

    @application.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/health/ready")
    def ready() -> dict[str, str]:
        if os.getenv("METAL_BACKEND", "development") == "mlx" and not detected.metal_supported:
            raise HTTPException(status_code=503, detail="MLX backend requires Apple Metal")
        return {"status": "ready", "backend": os.getenv("METAL_BACKEND", "development")}

    @application.get("/metrics")
    def metrics() -> Response:
        ACTIVE.set(scheduler.active)
        QUEUED.set(scheduler.queue.qsize())
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.get("/v1/models")
    def models() -> dict:
        return {"object": "list", "data": [{"id": selected_model.model_id, "object": "model", "owned_by": "openmodelops"}]}

    @application.get("/v1/runtime/profile")
    def runtime_profile() -> dict:
        return {
            "hardware": detected.public_dict(),
            "model": {
                "id": selected_model.model_id,
                "parameter_billions": selected_model.parameter_billions,
                "weight_bits": selected_model.weight_bits,
                "kv_bits": selected_model.kv_bits,
                "estimated_weights_gb": selected_model.estimated_weights_gb,
            },
            "capacity": {"maximum_slots": scheduler.slots, "queue_limit": scheduler.queue.maxsize},
        }

    @application.post("/v1/runtime/plan")
    def plan(request: PlanRequest) -> dict:
        return planner.decide(
            AdmissionRequest(request.prompt_tokens, request.max_tokens, request.active_slots, request.multimodal)
        ).__dict__

    @application.post("/v1/chat/completions")
    async def chat(request: ChatCompletionRequest) -> dict:
        if request.stream:
            raise HTTPException(status_code=501, detail="streaming is planned for the native batch milestone")
        if request.model != selected_model.model_id:
            raise HTTPException(status_code=404, detail="model not loaded")
        prompt = _prompt(request.messages)
        prompt_tokens = estimate_tokens(prompt)
        decision = planner.decide(
            AdmissionRequest(prompt_tokens, request.max_tokens, scheduler.active, request.multimodal)
        )
        if not decision.admitted:
            REQUESTS.labels("rejected", "miss").inc()
            raise HTTPException(status_code=429, detail={"reason": decision.reason, "plan": decision.__dict__})
        maximum_tokens = min(request.max_tokens, max(1, decision.granted_context - prompt_tokens))
        if maximum_tokens < request.max_tokens:
            CLAMPED.inc()
        cached = cache.lookup(selected_model.model_id, prompt) is not None
        started = time.perf_counter()
        try:
            result = await scheduler.submit(prompt, maximum_tokens)
        except OverflowError as exc:
            REQUESTS.labels("queue_full", "hit" if cached else "miss").inc()
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except TimeoutError as exc:
            REQUESTS.labels("timeout", "hit" if cached else "miss").inc()
            raise HTTPException(status_code=504, detail="inference deadline exceeded") from exc
        LATENCY.observe(time.perf_counter() - started)
        REQUESTS.labels("success", "hit" if cached else "miss").inc()
        cache.record(selected_model.model_id, prompt, result.prompt_tokens)
        completion_id = f"chatcmpl-{uuid.uuid4().hex}"
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": selected_model.model_id,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": result.text}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.prompt_tokens + result.completion_tokens,
            },
            "openmodelops": {
                "cache_hit": cached,
                "admission": decision.reason,
                "granted_context": decision.granted_context,
            },
        }

    return application


app = create_app()
