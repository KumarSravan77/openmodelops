import pytest

from platforms.evaluation.adapters import deepeval_adapter, ragas_adapter
from platforms.evaluation.contracts import EvaluationCase, EvaluationGate

CASES = [EvaluationCase("case-1", "What is the limit?", "Ten", ("The limit is ten.",), "Ten")]


def test_two_engines_must_both_pass():
    good = {"answer_relevancy": 0.91, "faithfulness": 0.98, "context_precision": 0.88}
    tools = {"answer_relevancy": 0.92, "faithfulness": 0.97, "tool_correctness": 1.0}
    reports = EvaluationGate([ragas_adapter(lambda _: good), deepeval_adapter(lambda _: tools)]).run(CASES)
    assert [report.engine for report in reports] == ["ragas", "deepeval"]
    assert all(report.passed for report in reports)


def test_failed_metric_blocks_promotion():
    scores = {"answer_relevancy": 0.9, "faithfulness": 0.4, "context_precision": 0.9}
    with pytest.raises(ValueError, match="ragas"):
        EvaluationGate([ragas_adapter(lambda _: scores)]).run(CASES)


def test_missing_metric_and_empty_dataset_fail_closed():
    with pytest.raises(ValueError, match="omitted"):
        ragas_adapter(lambda _: {"faithfulness": 1.0}).evaluate(CASES)
    with pytest.raises(ValueError, match="cannot be empty"):
        EvaluationGate([ragas_adapter(lambda _: {})]).run([])
