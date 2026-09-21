from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from sqlalchemy import Column, MetaData, String, Table, Text, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
aria_evidence = Table(
    "aria_incident_evidence",
    metadata,
    Column("signal_id", String(128), primary_key=True),
    Column("nonce", String(128), nullable=False, unique=True),
    Column("received_at", String(64), nullable=False),
    Column("payload", Text, nullable=False),
)


class IntelligenceVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class AriaIntelligenceVerifier:
    secret: str
    tolerance_seconds: int = 300

    def verify(self, body: bytes, timestamp: str, nonce: str, signature: str) -> dict:
        if not self.secret or not timestamp or not nonce or not signature:
            raise IntelligenceVerificationError("signed ARIA headers are required")
        try:
            observed = int(timestamp)
        except ValueError as exc:
            raise IntelligenceVerificationError("invalid ARIA timestamp") from exc
        if abs(int(time.time()) - observed) > self.tolerance_seconds:
            raise IntelligenceVerificationError("ARIA message is outside the replay window")
        message = timestamp.encode() + b"." + nonce.encode() + b"." + body
        expected = "sha256=" + hmac.new(self.secret.encode(), message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise IntelligenceVerificationError("ARIA signature verification failed")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise IntelligenceVerificationError("ARIA payload is not valid JSON") from exc
        if payload.get("source") != "aria" or payload.get("schema_version") != "1.0" or not payload.get("signal_id"):
            raise IntelligenceVerificationError("unsupported ARIA intelligence contract")
        return payload


class AriaIntelligenceStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        metadata.create_all(engine)

    def record(self, payload: dict, nonce: str, received_at: str) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(aria_evidence).values(
                        signal_id=payload["signal_id"], nonce=nonce, received_at=received_at,
                        payload=json.dumps(payload, sort_keys=True),
                    )
                )
        except IntegrityError as exc:
            raise IntelligenceVerificationError("ARIA signal or nonce was already accepted") from exc

    def scorecard(self, tenant: str, workload_id: str) -> dict:
        with self.engine.connect() as connection:
            rows = connection.execute(select(aria_evidence.c.payload)).scalars().all()
        matching = []
        for row in rows:
            payload = json.loads(row)
            if payload.get("tenant") == tenant and payload.get("workload_id") == workload_id:
                matching.append(payload)
        severity_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        highest = max(matching, key=lambda item: severity_rank.get(item.get("severity", "low"), 0), default=None)
        return {
            "workload_id": workload_id,
            "signals": len(matching),
            "critical_or_high": sum(item.get("severity") in {"critical", "high"} for item in matching),
            "highest_severity": highest.get("severity") if highest else None,
            "minimum_confidence": min((float(item.get("confidence", 0)) for item in matching), default=None),
            "release_gate_impact": "fail-candidate"
            if highest and highest.get("severity") in {"critical", "high"}
            else "none",
            "automatic_promotion": False,
        }
