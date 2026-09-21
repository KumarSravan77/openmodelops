from __future__ import annotations

import argparse
import json
from pathlib import Path

from platforms.banking.synthetic import transactions


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic Canadian banking transactions")
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--fraud-ratio", type=float, default=0.02)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.count < 1 or not 0 <= args.fraud_ratio <= 1:
        parser.error("count must be positive and fraud-ratio must be between 0 and 1")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as destination:
        for transaction in transactions(args.count, args.seed, args.fraud_ratio):
            destination.write(json.dumps(transaction, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
