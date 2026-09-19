from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from platforms.factory.domain import FactorySpec


@dataclass(frozen=True)
class EvidenceStatement:
    workload_id: str
    gate: str
    evidence_uri: str
    evidence_digest: str
    evaluator: str

    def __post_init__(self) -> None:
        if not self.evidence_uri.startswith(("https://", "s3://", "oci://", "file://")):
            raise ValueError("evidence URI uses an unsupported scheme")
        if not self.evidence_digest.startswith("sha256:"):
            raise ValueError("evidence must use a sha256 digest")

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":")).encode()


class EvidenceVerifier:
    def __init__(self, public_keys: Mapping[str, bytes]) -> None:
        self.public_keys = dict(public_keys)

    def verify(self, statement: EvidenceStatement, key_id: str, signature: str) -> None:
        encoded_key = self.public_keys.get(key_id)
        if encoded_key is None:
            raise ValueError("untrusted evidence signing key")
        try:
            key = Ed25519PublicKey.from_public_bytes(encoded_key)
            key.verify(base64.b64decode(signature, validate=True), statement.canonical_bytes())
        except Exception as exc:
            raise ValueError("evidence signature verification failed") from exc


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    policy_digest: str
    reasons: tuple[str, ...]


class FactoryPolicy:
    VERSION = "factory-policy-v1"

    def evaluate(self, spec: FactorySpec) -> PolicyDecision:
        reasons: list[str] = []
        if spec.environment == "production" and spec.internet_egress:
            reasons.append("production workloads require approved private egress")
        if spec.data_classification == "restricted" and spec.internet_egress:
            reasons.append("restricted data cannot use internet egress")
        if spec.requires_gpu and spec.slo.availability_target > 0.9999:
            reasons.append("GPU availability target requires a reviewed multi-zone capacity plan")
        digest = hashlib.sha256(self.VERSION.encode()).hexdigest()
        return PolicyDecision(not reasons, f"sha256:{digest}", tuple(reasons))
