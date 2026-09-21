from __future__ import annotations

import asyncio
import sys
from types import ModuleType

from fastapi.testclient import TestClient

from platforms.metal_runtime.api import create_app
from platforms.metal_runtime.backend import DevelopmentBackend, MLXBackend
from platforms.metal_runtime.cache import PromptCacheIndex
from platforms.metal_runtime.hardware import HardwareProfile
from platforms.metal_runtime.planner import AdmissionRequest, MemoryPlanner, ModelProfile
from platforms.metal_runtime.scheduler import BoundedScheduler

HARDWARE = HardwareProfile("macOS", "Apple M3 Pro", 36, 12, 18, True)
MODEL = ModelProfile("test-qwen", 27, weight_bits=4, kv_bytes_per_token_fp16=65536, kv_bits=4)


def test_27b_model_has_a_safe_context_budget() -> None:
    planner = MemoryPlanner(36, MODEL, maximum_slots=2)
    decision = planner.decide(AdmissionRequest(64_000, 4096))
    assert decision.admitted
    assert decision.granted_context == 68_096
    assert decision.estimated_memory_gb <= 36


def test_planner_rejects_an_unsafe_second_slot() -> None:
    planner = MemoryPlanner(36, MODEL, maximum_slots=1)
    decision = planner.decide(AdmissionRequest(1000, 1000, active_slots=1))
    assert not decision.admitted
    assert decision.reason == "concurrency_limit"


def test_prompt_cache_is_hashed_and_lru_bounded() -> None:
    cache = PromptCacheIndex(capacity=1)
    first = cache.record("model", "private prompt", 3)
    cache.record("model", "new prompt", 2)
    assert "private prompt" not in first.key
    assert cache.lookup("model", "private prompt") is None
    assert len(cache) == 1


def test_two_slot_scheduler_processes_concurrent_requests() -> None:
    async def exercise() -> None:
        scheduler = BoundedScheduler(DevelopmentBackend(), slots=2, queue_limit=2)
        await scheduler.start()
        first, second = await asyncio.gather(scheduler.submit("first", 10), scheduler.submit("second", 10))
        await scheduler.stop()
        assert first.text and second.text

    asyncio.run(exercise())


def test_openai_compatible_completion_and_cache_hit() -> None:
    app = create_app(HARDWARE, ModelProfile("test-qwen", 8), DevelopmentBackend())
    payload = {"model": "test-qwen", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 16}
    with TestClient(app) as client:
        first = client.post("/v1/chat/completions", json=payload)
        second = client.post("/v1/chat/completions", json=payload)
        profile = client.get("/v1/runtime/profile")
    assert first.status_code == 200
    assert first.json()["object"] == "chat.completion"
    assert first.json()["openmodelops"]["cache_hit"] is False
    assert second.json()["openmodelops"]["cache_hit"] is True
    assert profile.json()["hardware"]["memory_gb"] == 36


def test_streaming_fails_explicitly_until_implemented() -> None:
    app = create_app(HARDWARE, ModelProfile("test-qwen", 8), DevelopmentBackend())
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "test-qwen", "messages": [{"role": "user", "content": "hello"}], "stream": True},
        )
    assert response.status_code == 501


def test_mlx_backend_applies_chat_template_and_reports_tokenizer_counts(monkeypatch) -> None:
    calls: dict = {}

    class Tokenizer:
        has_chat_template = True

        def apply_chat_template(self, messages, **kwargs):
            calls.update(kwargs)
            return f"templated:{messages[0]['content']}"

        def encode(self, value):
            return value.split(":")

    fake = ModuleType("mlx_lm")
    fake.load = lambda _: (object(), Tokenizer())
    fake.generate = lambda _model, _tokenizer, **kwargs: f"answer:{kwargs['prompt']}"
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)

    result = asyncio.run(MLXBackend("model").generate("hello", 8))

    assert calls["add_generation_prompt"] is True
    assert calls["enable_thinking"] is False
    assert result.prompt_tokens == 2
    assert result.completion_tokens == 3
