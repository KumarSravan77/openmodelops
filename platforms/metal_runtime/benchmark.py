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


def _stream_request(url: str, payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, json.dumps(payload).encode(), headers, method="POST")
    started = time.perf_counter()
    first_token_at: float | None = None
    last_token_at: float | None = None
    last_index = 0
    final: dict[str, Any] | None = None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        for raw_line in response:
            if not raw_line.startswith(b"data: "):
                continue
            data = raw_line[6:].strip()
            if data == b"[DONE]":
                break
            event = json.loads(data)
            if "error" in event:
                raise RuntimeError("Inference stream failed")
            index = event.get("openmodelops", {}).get("token_index")
            if isinstance(index, int) and index > last_index:
                last_index = index
                last_token_at = time.perf_counter()
                if first_token_at is None:
                    first_token_at = last_token_at
            if "usage" in event:
                final = event
    if final is None:
        raise ValueError("Stream ended without usage")
    final["client_visible_ttft_seconds"] = first_token_at - started if first_token_at is not None else None
    final["client_visible_tpot_seconds"] = (
        (last_token_at - first_token_at) / (last_index - 1)
        if first_token_at is not None and last_token_at is not None and last_index > 1 else None
    )
    return final


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
    cost_model: dict[str, float] | None = None,
    stream: bool = False,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("Benchmark is limited to a loopback model endpoint")
    if not concurrency_levels or any(level < 1 for level in concurrency_levels) or requests_per_level < 1:
        raise ValueError("Concurrency and request counts must be positive")
    if cost_model is not None and (
        set(cost_model) != {"hardware_usd_per_hour", "average_watts", "electricity_usd_per_kwh"}
        or any(not math.isfinite(value) or value < 0 for value in cost_model.values())
    ):
        raise ValueError("Cost model requires three non-negative, finite inputs")
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
        if stream:
            payload["stream"] = True
        started = time.perf_counter()
        try:
            response = (
                _stream_request(base_url + "/v1/chat/completions", payload, api_key, timeout)
                if stream else _json_request(base_url + "/v1/chat/completions", payload, api_key, timeout)
            )
            return {
                "ok": True,
                "latency_seconds": time.perf_counter() - started,
                "prompt_tokens": response["usage"]["prompt_tokens"],
                "completion_tokens": response["usage"]["completion_tokens"],
                "cache_hit": response.get("openmodelops", {}).get("cache_hit", False),
                "queue_wait_seconds": response.get("openmodelops", {}).get("queue_wait_seconds", 0.0),
                "backend_first_token_seconds": response.get("openmodelops", {}).get("backend_first_token_seconds"),
                "backend_time_per_output_token_seconds": response.get("openmodelops", {}).get(
                    "backend_time_per_output_token_seconds"
                ),
                "client_visible_ttft_seconds": response.get("client_visible_ttft_seconds"),
                "client_visible_tpot_seconds": response.get("client_visible_tpot_seconds"),
            }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError, RuntimeError) as exc:
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
        first_tokens = [
            sample["backend_first_token_seconds"] for sample in successful
            if sample["backend_first_token_seconds"] is not None
        ]
        token_intervals = [
            sample["backend_time_per_output_token_seconds"] for sample in successful
            if sample["backend_time_per_output_token_seconds"] is not None
        ]
        client_first_tokens = [
            sample["client_visible_ttft_seconds"] for sample in successful
            if sample["client_visible_ttft_seconds"] is not None
        ]
        client_token_intervals = [
            sample["client_visible_tpot_seconds"] for sample in successful
            if sample["client_visible_tpot_seconds"] is not None
        ]
        completion_tokens = sum(sample["completion_tokens"] for sample in successful)
        modeled_cost = (
            wall_seconds / 3600 * (
                cost_model["hardware_usd_per_hour"]
                + cost_model["average_watts"] / 1000 * cost_model["electricity_usd_per_kwh"]
            )
            if cost_model is not None else None
        )
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
            "backend_first_token_p50_seconds": _percentile(first_tokens, 0.5),
            "backend_first_token_p95_seconds": _percentile(first_tokens, 0.95),
            "backend_tpot_p50_seconds": _percentile(token_intervals, 0.5),
            "backend_tpot_p95_seconds": _percentile(token_intervals, 0.95),
            "client_ttft_p50_seconds": _percentile(client_first_tokens, 0.5),
            "client_ttft_p95_seconds": _percentile(client_first_tokens, 0.95),
            "client_tpot_p50_seconds": _percentile(client_token_intervals, 0.5),
            "client_tpot_p95_seconds": _percentile(client_token_intervals, 0.95),
            "completion_tokens": completion_tokens,
            "aggregate_completion_tokens_per_second": round(completion_tokens / wall_seconds, 3) if wall_seconds else None,
            "requests_per_second": round(len(successful) / wall_seconds, 3) if wall_seconds else None,
            "modeled_cost_usd": round(modeled_cost, 8) if modeled_cost is not None else None,
            "modeled_cost_per_output_token_usd": round(modeled_cost / completion_tokens, 10)
            if modeled_cost is not None and completion_tokens else None,
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
        "streaming": stream,
        "cost_model": cost_model,
        "warmup_latency_seconds": round(warmup["latency_seconds"], 4),
        "profiles": profiles,
        "limitations": [
            "Backend first-token timing excludes queue and network; client TTFT/TPOT require --stream",
            "Cost per output token is modeled from user-entered hardware, power and electricity assumptions; not billed cost",
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
    parser.add_argument("--stream", action="store_true", help="Use SSE for client-visible TTFT and TPOT")
    parser.add_argument("--hardware-usd-per-hour", type=float)
    parser.add_argument("--average-watts", type=float)
    parser.add_argument("--electricity-usd-per-kwh", type=float)
    args = parser.parse_args()
    cost_inputs = (args.hardware_usd_per_hour, args.average_watts, args.electricity_usd_per_kwh)
    if any(value is not None for value in cost_inputs) and not all(value is not None for value in cost_inputs):
        parser.error("Supply all three cost inputs or none")
    cost_model = dict(zip(
        ("hardware_usd_per_hour", "average_watts", "electricity_usd_per_kwh"), cost_inputs, strict=True
    )) if all(value is not None for value in cost_inputs) else None
    result = asyncio.run(benchmark(
        args.base_url,
        os.getenv("METAL_API_KEY", ""),
        [int(value) for value in args.concurrency.split(",")],
        args.requests,
        args.max_tokens,
        args.timeout,
        args.require_real_model,
        cost_model,
        args.stream,
    ))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all(profile["errors"] == 0 for profile in result["profiles"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
