from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.contracts import ModelEndpoint
from platforms.agents.providers import OpenAICompatibleModel, UrllibTransport
from platforms.judgeops.calibration import CalibrationCase, CalibrationPolicy, calibrate
from platforms.judgeops.contracts import Verdict
from platforms.judgeops.datasets import load_golden_dataset
from platforms.judgeops.ensemble import EnsembleJudge
from platforms.judgeops.providers import DeterministicJudge, OpenAIJudge
from platforms.judgeops.rubrics import RUBRICS
from platforms.judgeops.shadow import ShadowEvaluator


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a non-authoritative local judge shadow and calibration experiment.")
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/golden/judgeops-rag.jsonl"))
    parser.add_argument("--rubric", default="rag-grounded-answer", choices=sorted(RUBRICS))
    parser.add_argument("--base-url", default="http://127.0.0.1:8008")
    parser.add_argument("--model", default="mlx-community/Qwen3-0.6B-4bit")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    cases = load_golden_dataset(args.dataset)
    rubric = RUBRICS[args.rubric]
    endpoint = ModelEndpoint("candidate-judge", args.model, args.base_url, timeout_seconds=120)
    candidate = OpenAIJudge(
        OpenAICompatibleModel(UrllibTransport(), args.api_key), endpoint, "local-qwen-candidate", args.model
    )
    active_ensemble = EnsembleJudge([DeterministicJudge()])
    candidate_ensemble = EnsembleJudge([candidate])
    shadow = ShadowEvaluator(active_ensemble, candidate_ensemble).run(
        [case.sample for case in cases], rubric
    )
    by_id = {comparison.sample_id: comparison for comparison in shadow.comparisons}
    provider_errors = [item.sample_id for item in shadow.comparisons if item.candidate_error]
    unresolved = [item.sample_id for item in shadow.comparisons if item.candidate_verdict == Verdict.REVIEW]
    calibration = None
    failures: tuple[str, ...] = ("provider_errors",) if provider_errors else ()
    if unresolved:
        failures += ("unresolved_reviews",)
    if not unresolved and not provider_errors:
        calibration = calibrate(
            [
                CalibrationCase(
                    case.sample.sample_id,
                    case.human_verdict == Verdict.PASS,
                    Verdict(by_id[case.sample.sample_id].candidate_verdict),
                    (
                        by_id[case.sample.sample_id].candidate_confidence
                        if by_id[case.sample.sample_id].candidate_verdict == Verdict.PASS
                        else 1 - by_id[case.sample.sample_id].candidate_confidence
                    ),
                )
                for case in cases
            ]
        )
        failures = CalibrationPolicy().failures(calibration)
    payload = {
        "mode": "shadow_only",
        "candidate": {"provider": "openai-compatible", "model": args.model, "base_url": args.base_url},
        "dataset": str(args.dataset),
        "rubric_digest": rubric.digest,
        "shadow_agreement_rate": shadow.agreement_rate,
        "calibration": calibration.__dict__ if calibration else None,
        "unresolved_reviews": unresolved,
        "provider_errors": provider_errors,
        "production_qualified": not failures,
        "qualification_failures": failures,
        "comparisons": [item.__dict__ for item in shadow.comparisons],
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
