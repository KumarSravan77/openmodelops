from __future__ import annotations

import asyncio

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
    assert result["profiles"][0]["ttft_seconds"] is None
