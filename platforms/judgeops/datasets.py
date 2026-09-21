from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .contracts import JudgeSample, Verdict


@dataclass(frozen=True)
class GoldenCase:
    sample: JudgeSample
    human_verdict: Verdict


def load_golden_dataset(path: Path) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    identifiers: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            sample = JudgeSample.model_validate(payload["sample"])
            verdict = Verdict(payload["human_verdict"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid golden case at line {line_number}") from exc
        if verdict == Verdict.REVIEW:
            raise ValueError("golden cases require resolved pass/fail human labels")
        if sample.sample_id in identifiers:
            raise ValueError(f"duplicate golden sample ID: {sample.sample_id}")
        identifiers.add(sample.sample_id)
        cases.append(GoldenCase(sample, verdict))
    if len(cases) < 2:
        raise ValueError("golden dataset requires at least two labelled cases")
    return cases
