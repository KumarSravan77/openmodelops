from __future__ import annotations

import argparse
import json
from pathlib import Path

from platforms.judgeops.annotation import AnnotationLedger
from platforms.judgeops.contracts import Verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently label and promote JudgeOps candidate cases.")
    parser.add_argument("--database", default="judgeops-annotations.db")
    subparsers = parser.add_subparsers(dest="action", required=True)

    label = subparsers.add_parser("label")
    label.add_argument("--sample-id", required=True)
    label.add_argument("--reviewer", required=True)
    label.add_argument("--verdict", choices=["pass", "fail"], required=True)
    label.add_argument("--rationale", required=True)

    status = subparsers.add_parser("status")
    status.add_argument("--sample-id", required=True)

    export = subparsers.add_parser("export")
    export.add_argument("--candidates", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    ledger = AnnotationLedger(args.database)
    if args.action == "label":
        ledger.label(args.sample_id, args.reviewer, Verdict(args.verdict), args.rationale)
        result = ledger.status(args.sample_id)
    elif args.action == "status":
        result = ledger.status(args.sample_id)
    else:
        result = ledger.export_consensus(args.candidates, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
