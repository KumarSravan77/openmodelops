from datetime import UTC, datetime

from fastapi.testclient import TestClient

from platforms.banking.api import app
from platforms.banking.domain import Decision, Transaction, decision_for, privacy_safe_account_hash, score
from platforms.banking.synthetic import transactions


def transaction(**overrides) -> Transaction:
    values = {
        "event_id": "event-000001",
        "account_token": "opaque-account-token",
        "amount_cad": "85.25",
        "province": "ON",
        "channel": "card_present",
        "merchant_category": "grocery",
        "occurred_at": datetime.now(UTC).isoformat(),
        "device_trusted": True,
        "international": False,
        "transactions_last_10m": 2,
        "failed_auth_last_24h": 0,
    }
    values.update(overrides)
    return Transaction.model_validate(values)


def test_baseline_transaction_is_approved() -> None:
    result = score(transaction())
    assert decision_for(result.score) == Decision.APPROVE
    assert result.reasons == ("BASELINE_ACTIVITY",)


def test_high_velocity_untrusted_transaction_is_declined() -> None:
    result = score(
        transaction(
            amount_cad="12500.00",
            channel="ecommerce",
            device_trusted=False,
            international=True,
            transactions_last_10m=14,
            failed_auth_last_24h=5,
        )
    )
    assert decision_for(result.score) == Decision.DECLINE
    assert result.score == 1.0


def test_api_is_idempotent() -> None:
    client = TestClient(app)
    payload = transaction(event_id="idempotent-0001").model_dump(mode="json")
    first = client.post("/v1/transactions/score", json=payload)
    second = client.post("/v1/transactions/score", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["risk_score"] == second.json()["risk_score"]


def test_generator_is_deterministic_and_contains_no_direct_identity() -> None:
    first = list(transactions(5, seed=42, fraud_ratio=0.2))
    second = list(transactions(5, seed=42, fraud_ratio=0.2))
    assert first == second
    assert all(item["amount_cad"] and item["account_token"].startswith("acct_") for item in first)
    assert all("name" not in item and "address" not in item and "sin" not in item for item in first)


def test_account_hash_does_not_expose_token() -> None:
    token = "opaque-account-token"
    value = privacy_safe_account_hash(token)
    assert token not in value
    assert len(value) == 16
