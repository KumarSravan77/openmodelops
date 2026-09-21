import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import create_engine

from platforms.integrations.aria_intelligence import (
    AriaIntelligenceStore,
    AriaIntelligenceVerifier,
    IntelligenceVerificationError,
)


def signed(secret="secret", timestamp=None, nonce="nonce-1"):
    payload = {"schema_version": "1.0", "source": "aria", "signal_id": "signal-1", "service": "api"}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = timestamp or str(int(time.time()))
    message = timestamp.encode() + b"." + nonce.encode() + b"." + body
    signature = "sha256=" + hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return body, timestamp, nonce, signature


def test_verifies_exact_aria_contract_and_persists_once():
    body, timestamp, nonce, signature = signed()
    payload = AriaIntelligenceVerifier("secret").verify(body, timestamp, nonce, signature)
    store = AriaIntelligenceStore(create_engine("sqlite:///:memory:"))
    store.record(payload, nonce, "2026-01-01T00:00:00+00:00")
    with pytest.raises(IntelligenceVerificationError, match="already accepted"):
        store.record(payload, nonce, "2026-01-01T00:00:01+00:00")


def test_rejects_tampering_and_expired_replay():
    body, timestamp, nonce, signature = signed()
    verifier = AriaIntelligenceVerifier("secret")
    with pytest.raises(IntelligenceVerificationError, match="signature"):
        verifier.verify(body + b" ", timestamp, nonce, signature)
    expired = str(int(time.time()) - 301)
    body, _, nonce, signature = signed(timestamp=expired)
    with pytest.raises(IntelligenceVerificationError, match="replay window"):
        verifier.verify(body, expired, nonce, signature)
