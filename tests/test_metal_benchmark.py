from __future__ import annotations

import asyncio
import io
import json

import pytest

from platforms.metal_runtime import benchmark as bench


def test_percentile_handles_empty_and_small_samples() -> None:
    assert bench._percentile([], 0.95) is None
    assert bench._percentile([0.3, 0.1, 0.2], 0.5) == 0.2
    assert bench._percentile([0.3, 0.1, 0.2], 0.95) == 0.3


def test_benchmark_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="loopback"):
        asyncio.run(bench.benchmark("https://example.com", "", [1], 1, 8))


def test_benchmark_refuses_synthetic_backend_when_real_required(monkeypatch) -> None:
    def fake_request(url, payload, api_key, timeout):
        if url.endswith("/health/ready"):
            return {"backend": "development"}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "test-model"}]}
        return {"hardware": {}, "capacity": {}}

    monkeypatch.setattr(bench, "_json_request", fake_request)
    with pytest.raises(RuntimeError, match="synthetic"):
        asyncio.run(bench.benchmark("http://127.0.0.1:8008", "", [1], 1, 8, require_real_model=True))


def test_benchmark_labels_synthetic_and_never_invents_ttft(monkeypatch) -> None:
    def fake_request(url, payload, api_key, timeout):
        if url.endswith("/health/ready"):
            return {"backend": "development"}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "test-model"}]}
        if url.endswith("/v1/runtime/profile"):
            return {"hardware": {"memory_gb": 36}, "capacity": {"maximum_slots": 2}}
        return {
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            "openmodelops": {"cache_hit": False, "queue_wait_seconds": 0.01},
        }

    monkeypatch.setattr(bench, "_json_request", fake_request)
    result = asyncio.run(bench.benchmark("http://127.0.0.1:8008", "", [1], 2, 8))
    assert result["evidence_mode"] == "synthetic-development"
    assert result["profiles"][0]["successes"] == 2
    assert result["profiles"][0]["client_ttft_p50_seconds"] is None


def test_benchmark_cost_requires_explicit_valid_assumptions(monkeypatch) -> None:
    def fake_request(url, payload, api_key, timeout):
        if url.endswith("/health/ready"):
            return {"backend": "mlx"}
        if url.endswith("/v1/models"):
            return {"data": [{"id": "test-model"}]}
        if url.endswith("/v1/runtime/profile"):
            return {"hardware": {}, "capacity": {}}
        return {"usage": {"prompt_tokens": 5, "completion_tokens": 3}, "openmodelops": {}}

    monkeypatch.setattr(bench, "_json_request", fake_request)
    base = "http://127.0.0.1:8008"
    with pytest.raises(ValueError, match="Cost model"):
        asyncio.run(bench.benchmark(base, "", [1], 1, 8, cost_model={"average_watts": -10}))
    assumptions = {"hardware_usd_per_hour": 0.1, "average_watts": 25.0, "electricity_usd_per_kwh": 0.2}
    result = asyncio.run(bench.benchmark(base, "", [1], 1, 8, cost_model=assumptions))
    assert result["profiles"][0]["modeled_cost_per_output_token_usd"] is not None
    assert result["cost_model"] == assumptions


def test_stream_reader_counts_token_events_without_storing_text(monkeypatch) -> None:
    first = {"openmodelops": {"token_index": 1}, "choices": [{"delta": {"content": "secret"}}]}
    second = {"openmodelops": {"token_index": 2}, "choices": [{"delta": {"content": "answer"}}]}
    final = {"usage": {"prompt_tokens": 2, "completion_tokens": 2}, "openmodelops": {}}
    body = b"".join(f"data: {json.dumps(event)}\n\n".encode() for event in (first, second, final))
    body += b"data: [DONE]\n\n"
    monkeypatch.setattr(bench.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(body))
    result = bench._stream_request("http://127.0.0.1:8008/v1/chat/completions", {"stream": True}, "", 5)
    assert result["usage"]["completion_tokens"] == 2
    assert result["client_visible_ttft_seconds"] is not None
    assert result["client_visible_tpot_seconds"] is not None
    assert "secret" not in json.dumps(result)
