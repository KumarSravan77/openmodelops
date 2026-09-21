from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict

from fastapi import FastAPI, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from platforms.banking.domain import ScoreResponse, Transaction, decision_for, score

app = FastAPI(title="MapleShield Synthetic Banking Workload", version="1.0.0")
MODEL_VERSION = "rules-v1"

REQUESTS = Counter("banking_score_requests_total", "Scoring requests", ["decision", "duplicate"])
LATENCY = Histogram(
    "banking_score_duration_seconds",
    "Fraud scoring latency",
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
MAX_IDEMPOTENCY_KEYS = int(os.getenv("BANKING_MAX_IDEMPOTENCY_KEYS", "100000"))
_seen: OrderedDict[str, ScoreResponse] = OrderedDict()
_lock = threading.Lock()


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "model_version": MODEL_VERSION}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/transactions/score", response_model=ScoreResponse, status_code=status.HTTP_200_OK)
def score_transaction(transaction: Transaction) -> ScoreResponse:
    started = time.perf_counter()
    with _lock:
        previous = _seen.get(transaction.event_id)
        if previous:
            _seen.move_to_end(transaction.event_id)
            duplicate = previous.model_copy(update={"duplicate": True})
            REQUESTS.labels(decision=duplicate.decision, duplicate="true").inc()
            LATENCY.observe(time.perf_counter() - started)
            return duplicate
        result = score(transaction)
        response = ScoreResponse(
            event_id=transaction.event_id,
            decision=decision_for(result.score),
            risk_score=result.score,
            reason_codes=list(result.reasons),
            model_version=MODEL_VERSION,
        )
        _seen[transaction.event_id] = response
        if len(_seen) > MAX_IDEMPOTENCY_KEYS:
            _seen.popitem(last=False)
    REQUESTS.labels(decision=response.decision, duplicate="false").inc()
    LATENCY.observe(time.perf_counter() - started)
    return response
