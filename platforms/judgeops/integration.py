from __future__ import annotations

from dataclasses import dataclass

from platforms.evaluation.contracts import EvaluationCase, EvaluationReport, MetricResult

from .contracts import JudgeSample, Rubric, Verdict
from .ensemble import EnsembleJudge


@dataclass
class JudgeOpsEvaluationAdapter:
    ensemble: EnsembleJudge
    rubric: Rubric

    @property
    def name(self) -> str:
        return f"judgeops:{self.rubric.rubric_id}"

    def evaluate(self, cases: list[EvaluationCase]) -> EvaluationReport:
        if not cases:
            raise ValueError("JudgeOps evaluation dataset cannot be empty")
        results = [
            self.ensemble.evaluate(
                JudgeSample(
                    sample_id=case.case_id,
                    question=case.question,
                    candidate_answer=case.answer,
                    reference_answer=case.expected_answer,
                    contexts=list(case.contexts),
                    expected_tools=list(case.expected_tools),
                ),
                self.rubric,
            )
            for case in cases
        ]
        review_cases = sum(result.verdict == Verdict.REVIEW for result in results)
        failed_cases = sum(result.verdict == Verdict.FAIL for result in results)
        metrics = tuple(
            MetricResult(
                dimension.name,
                min(result.scores[dimension.name] for result in results),
                dimension.threshold,
                "Worst-case score; every release case must satisfy the rubric.",
            )
            for dimension in self.rubric.dimensions
        )
        return EvaluationReport(
            self.name,
            metrics,
            len(cases),
            {
                "rubric_digest": self.rubric.digest,
                "review_cases": str(review_cases),
                "failed_cases": str(failed_cases),
            },
        )
