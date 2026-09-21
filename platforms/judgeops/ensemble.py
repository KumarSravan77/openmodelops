from __future__ import annotations

import statistics
from dataclasses import dataclass

from .contracts import JudgeResult, JudgeSample, Rubric, Verdict
from .providers import JudgeProvider


@dataclass(frozen=True)
class EnsembleResult:
    sample_id: str
    verdict: Verdict
    scores: dict[str, float]
    weighted_score: float
    confidence: float
    maximum_disagreement: float
    judge_results: tuple[JudgeResult, ...]
    reason: str


class EnsembleJudge:
    def __init__(self, judges: list[JudgeProvider], maximum_disagreement: float = 0.25) -> None:
        if not judges:
            raise ValueError("at least one judge is required")
        identities = {(judge.judge_id, judge.judge_revision) for judge in judges}
        if len(identities) != len(judges):
            raise ValueError("ensemble judges must have unique identities")
        self.judges = judges
        self.maximum_disagreement = maximum_disagreement

    def evaluate(self, sample: JudgeSample, rubric: Rubric) -> EnsembleResult:
        results = tuple(judge.evaluate(sample, rubric) for judge in self.judges)
        scores: dict[str, float] = {}
        disagreement = 0.0
        for dimension in rubric.dimensions:
            values = [result.scores[dimension.name] for result in results]
            scores[dimension.name] = statistics.median(values)
            disagreement = max(disagreement, max(values) - min(values))
        total_weight = sum(dimension.weight for dimension in rubric.dimensions)
        weighted = sum(scores[dimension.name] * dimension.weight for dimension in rubric.dimensions) / total_weight
        confidence = statistics.median(result.confidence for result in results)
        injection = any(result.injection_detected for result in results)
        thresholds_pass = all(scores[dimension.name] >= dimension.threshold for dimension in rubric.dimensions)
        if injection:
            verdict, reason = Verdict.REVIEW, "judge-targeting prompt injection detected"
        elif disagreement > self.maximum_disagreement:
            verdict, reason = Verdict.REVIEW, "judge disagreement exceeded policy"
        elif confidence < rubric.minimum_confidence:
            verdict, reason = Verdict.REVIEW, "ensemble confidence below rubric policy"
        elif thresholds_pass:
            verdict, reason = Verdict.PASS, "all rubric thresholds passed"
        else:
            verdict, reason = Verdict.FAIL, "one or more rubric thresholds failed"
        return EnsembleResult(
            sample.sample_id,
            verdict,
            scores,
            round(weighted, 6),
            confidence,
            round(disagreement, 6),
            results,
            reason,
        )
