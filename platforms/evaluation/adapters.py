from __future__ import annotations

from collections.abc import Callable

from .contracts import EvaluationCase, EvaluationReport, MetricResult


class CallableEvaluationAdapter:
    """Boundary for Ragas, DeepEval, Langfuse, Opik or Phoenix evaluation runners.

    Provider SDK imports live in deployment-specific runners; the platform consumes
    normalized scores and applies one deterministic promotion policy.
    """

    def __init__(
        self,
        name: str,
        runner: Callable[[list[EvaluationCase]], dict[str, float]],
        thresholds: dict[str, float],
    ) -> None:
        self.name = name
        self.runner = runner
        self.thresholds = thresholds

    def evaluate(self, cases: list[EvaluationCase]) -> EvaluationReport:
        scores = self.runner(cases)
        missing = sorted(set(self.thresholds) - set(scores))
        if missing:
            raise ValueError(f"{self.name} omitted required metrics: {missing}")
        metrics = tuple(
            MetricResult(metric, float(scores[metric]), threshold) for metric, threshold in sorted(self.thresholds.items())
        )
        return EvaluationReport(self.name, metrics, len(cases))


def ragas_adapter(runner: Callable[[list[EvaluationCase]], dict[str, float]]) -> CallableEvaluationAdapter:
    return CallableEvaluationAdapter(
        "ragas",
        runner,
        {"answer_relevancy": 0.8, "context_precision": 0.8, "faithfulness": 0.9},
    )


def deepeval_adapter(runner: Callable[[list[EvaluationCase]], dict[str, float]]) -> CallableEvaluationAdapter:
    return CallableEvaluationAdapter(
        "deepeval",
        runner,
        {"answer_relevancy": 0.8, "faithfulness": 0.9, "tool_correctness": 0.9},
    )
