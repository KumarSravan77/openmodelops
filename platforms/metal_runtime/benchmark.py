"""Benchmark the running Metal API without storing prompts or model responses."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any


def _json_request(url: str, payload: dict[str, Any] | None, api_key: str, timeout: float) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * fraction) - 1)], 4)


async def benchmark(
    base_url: str,
    api_key: str,
    concurrency_levels: list[int],
    requests_per_level: int,
    max_tokens: int,
    timeout: float = 180,
    require_real_model: bool = False,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("Benchmark is limited to a loopback model endpoint")
    if not concurrency_levels or any(level < 1 for level in concurrency_levels) or requests_per_level < 1:
        raise ValueError("Concurrency and request counts must be positive")
    health, models, profile = await asyncio.gather(
        asyncio.to_thread(_json_request, base_url + "/health/ready", None, api_key, timeout),
        asyncio.to_thread(_json_request, base_url + "/v1/models", None, api_key, timeout),
        asyncio.to_thread(_json_request, base_url + "/v1/runtime/profile", None, api_key, timeout),
    )
    backend = health["backend"]
    if require_real_model and backend == "development":
        raise RuntimeError("Development backend is synthetic; real-model benchmark required")
    model = models["data"][0]["id"]

    def one_request(index: int) -> dict[str, Any]:
        # Vary wording to avoid confusing metadata cache hits with model KV reuse.
        prompt = f"In two short sentences, explain why a payment event consumer can lag. Case {index}."
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
        started = time.perf_counter()
        try:
            response = _json_request(base_url + "/v1/chat/completions", payload, api_key, timeout)
            return {
                "ok": True,
                "latency_seconds": time.perf_counter() - started,
                "prompt_tokens": response["usage"]["prompt_tokens"],
                "completion_tokens": response["usage"]["completion_tokens"],
                "cache_hit": response.get("openmodelops", {}).get("cache_hit", False),
                "queue_wait_seconds": response.get("openmodelops", {}).get("queue_wait_seconds", 0.0),
            }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            return {"ok": False, "latency_seconds": time.perf_counter() - started, "error_type": type(exc).__name__}

    warmup = await asyncio.to_thread(one_request, -1)
    if not warmup["ok"]:
        raise RuntimeError(f"Warmup failed: {warmup['error_type']}")
    profiles = []
    for concurrency in concurrency_levels:
        semaphore = asyncio.Semaphore(concurrency)

        async def limited(index: int, limit: asyncio.Semaphore = semaphore) -> dict[str, Any]:
            async with limit:
                return await asyncio.to_thread(one_request, index)

        started = time.perf_counter()
        samples = await asyncio.gather(*(limited(index + concurrency * 10_000) for index in range(requests_per_level)))
        wall_seconds = time.perf_counter() - started
        successful = [sample for sample in samples if sample["ok"]]
        latencies = [sample["latency_seconds"] for sample in successful]
        queue_waits = [sample["queue_wait_seconds"] for sample in successful]
        completion_tokens = sum(sample["completion_tokens"] for sample in successful)
        profiles.append({
            "concurrency": concurrency,
            "requests": requests_per_level,
            "successes": len(successful),
            "errors": len(samples) - len(successful),
            "error_types": sorted({sample["error_type"] for sample in samples if not sample["ok"]}),
            "wall_seconds": round(wall_seconds, 4),
            "latency_p50_seconds": _percentile(latencies, 0.5),
            "latency_p95_seconds": _percentile(latencies, 0.95),
            "latency_mean_seconds": round(statistics.mean(latencies), 4) if latencies else None,
            "queue_wait_p95_seconds": _percentile(queue_waits, 0.95),
            "completion_tokens": completion_tokens,
            "aggregate_completion_tokens_per_second": round(completion_tokens / wall_seconds, 3) if wall_seconds else None,
            "requests_per_second": round(len(successful) / wall_seconds, 3) if wall_seconds else None,
            "ttft_seconds": None,  # Non-streaming endpoint cannot reveal first-token time.
            "cache_hits": sum(bool(sample["cache_hit"]) for sample in successful),
        })
    return {
        "schema_version": "1.0",
        "measured_at": datetime.now(UTC).isoformat(),
        "backend": backend,
        "evidence_mode": "real-model" if backend != "development" else "synthetic-development",
        "model": model,
        "hardware": profile["hardware"],
        "capacity": profile["capacity"],
        "max_tokens_requested": max_tokens,
        "warmup_latency_seconds": round(warmup["latency_seconds"], 4),
        "profiles": profiles,
        "limitations": [
            "No time-to-first-token measurement without streaming",
            "Short smoke workload; not a sustained-load or quality evaluation",
            "Cache-hit counter is metadata only, not proof of KV-cache reuse",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8008")
    parser.add_argument("--concurrency", default="1,2")
    parser.add_argument("--requests", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=48)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--require-real-model", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(benchmark(
        args.base_url,
        os.getenv("METAL_API_KEY", ""),
        [int(value) for value in args.concurrency.split(",")],
        args.requests,
        args.max_tokens,
        args.timeout,
        args.require_real_model,
    ))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(profile["errors"] == 0 for profile in result["profiles"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
