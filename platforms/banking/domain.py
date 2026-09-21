from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class Channel(StrEnum):
    CARD_PRESENT = "card_present"
    ECOMMERCE = "ecommerce"
    TRANSFER = "transfer"
    BILL_PAYMENT = "bill_payment"


class Transaction(BaseModel):
    event_id: str = Field(min_length=8, max_length=128)
    account_token: str = Field(min_length=12, max_length=128)
    amount_cad: Decimal = Field(gt=0, le=Decimal(1000000), decimal_places=2)
    province: str
    channel: Channel
    merchant_category: str = Field(min_length=2, max_length=64)
    occurred_at: datetime
    device_trusted: bool = True
    international: bool = False
    transactions_last_10m: int = Field(default=1, ge=0, le=1000)
    failed_auth_last_24h: int = Field(default=0, ge=0, le=1000)

    @field_validator("province")
    @classmethod
    def recognized_province(cls, value: str) -> str:
        allowed = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}
        if value not in allowed:
            raise ValueError("province must be a Canadian province or territory code")
        return value

    @field_validator("occurred_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(UTC)


class Decision(StrEnum):
    APPROVE = "approve"
    REVIEW = "review"
    DECLINE = "decline"


class ScoreResponse(BaseModel):
    event_id: str
    decision: Decision
    risk_score: float = Field(ge=0, le=1)
    reason_codes: list[str]
    model_version: str
    duplicate: bool = False


@dataclass(frozen=True)
class ScoredTransaction:
    score: float
    reasons: tuple[str, ...]


def score(transaction: Transaction) -> ScoredTransaction:
    value = 0.02
    reasons: list[str] = []
    if transaction.amount_cad >= Decimal(5000):
        value += 0.28
        reasons.append("HIGH_AMOUNT")
    if transaction.international:
        value += 0.18
        reasons.append("INTERNATIONAL")
    if not transaction.device_trusted:
        value += 0.24
        reasons.append("UNTRUSTED_DEVICE")
    if transaction.transactions_last_10m >= 8:
        value += 0.25
        reasons.append("HIGH_VELOCITY")
    if transaction.failed_auth_last_24h >= 3:
        value += 0.25
        reasons.append("AUTH_FAILURES")
    if transaction.channel == Channel.ECOMMERCE:
        value += 0.04
    return ScoredTransaction(min(value, 1.0), tuple(reasons or ["BASELINE_ACTIVITY"]))


def decision_for(value: float) -> Decision:
    if value >= 0.70:
        return Decision.DECLINE
    if value >= 0.35:
        return Decision.REVIEW
    return Decision.APPROVE


def privacy_safe_account_hash(account_token: str) -> str:
    return hashlib.sha256(account_token.encode()).hexdigest()[:16]
