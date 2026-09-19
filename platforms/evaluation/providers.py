from __future__ import annotations

from typing import Any

from .contracts import EvaluationCase


def run_ragas(cases: list[EvaluationCase], metrics: list[Any], *, llm: Any = None, embeddings: Any = None) -> dict[str, float]:
    try:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
    except ImportError as exc:
        raise RuntimeError("install the 'evaluation' extra to run Ragas") from exc
    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=case.question,
                response=case.answer,
                retrieved_contexts=list(case.contexts),
                reference=case.expected_answer,
            )
            for case in cases
        ]
    )
    result = evaluate(dataset=dataset, metrics=metrics, llm=llm, embeddings=embeddings)
    return {key: float(value) for key, value in result.items() if isinstance(value, (int, float))}


def run_deepeval(cases: list[EvaluationCase], metrics: list[Any]) -> dict[str, float]:
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:
        raise RuntimeError("install the 'evaluation' extra to run DeepEval") from exc
    test_cases = [
        LLMTestCase(
            input=case.question,
            actual_output=case.answer,
            expected_output=case.expected_answer,
            retrieval_context=list(case.contexts),
        )
        for case in cases
    ]
    scores: dict[str, list[float]] = {}
    for metric in metrics:
        name = metric.__class__.__name__.removesuffix("Metric").lower()
        for test_case in test_cases:
            metric.measure(test_case)
            scores.setdefault(name, []).append(float(metric.score))
    return {name: sum(values) / len(values) for name, values in scores.items()}
