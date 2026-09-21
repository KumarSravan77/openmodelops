from __future__ import annotations

import random
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

PROVINCES = ("ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE")
CHANNELS = ("card_present", "ecommerce", "transfer", "bill_payment")
MERCHANTS = ("grocery", "fuel", "restaurant", "travel", "utilities", "electronics", "pharmacy")


def transactions(count: int, seed: int = 2026, fraud_ratio: float = 0.02) -> Iterator[dict]:
    rng = random.Random(seed)
    base = datetime(2026, 1, 15, 12, tzinfo=UTC)
    for index in range(count):
        suspicious = rng.random() < fraud_ratio
        amount = rng.uniform(10, 450) if not suspicious else rng.uniform(5_000, 25_000)
        yield {
            "event_id": str(uuid.UUID(int=rng.getrandbits(128))),
            "account_token": f"acct_{rng.getrandbits(96):024x}",
            "amount_cad": f"{amount:.2f}",
            "province": rng.choice(PROVINCES),
            "channel": rng.choice(CHANNELS),
            "merchant_category": rng.choice(MERCHANTS),
            "occurred_at": (base + timedelta(milliseconds=index * 20)).isoformat(),
            "device_trusted": not suspicious or rng.random() > 0.8,
            "international": suspicious and rng.random() < 0.7,
            "transactions_last_10m": rng.randint(1, 4) if not suspicious else rng.randint(8, 20),
            "failed_auth_last_24h": rng.randint(0, 1) if not suspicious else rng.randint(3, 8),
            "synthetic_label": "suspicious" if suspicious else "normal",
        }
