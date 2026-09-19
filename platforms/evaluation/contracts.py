from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    answer: str
    contexts: tuple[str, ...] = ()
    expected_answer: str | None = None
    expected_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricResult:
    name: str
    score: float
    threshold: float
    reason: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 1 or not 0 <= self.threshold <= 1:
            raise ValueError("evaluation scores and thresholds must be between 0 and 1")

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold


@dataclass(frozen=True)
class EvaluationReport:
    engine: str
    metrics: tuple[MetricResult, ...]
    case_count: int
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.case_count > 0 and bool(self.metrics) and all(metric.passed for metric in self.metrics)


class EvaluationEngine(Protocol):
    name: str

    def evaluate(self, cases: list[EvaluationCase]) -> EvaluationReport: ...


class EvaluationGate:
    def __init__(self, engines: list[EvaluationEngine]) -> None:
        if not engines:
            raise ValueError("at least one evaluation engine is required")
        self.engines = engines

    def run(self, cases: list[EvaluationCase]) -> tuple[EvaluationReport, ...]:
        if not cases:
            raise ValueError("evaluation dataset cannot be empty")
        reports = tuple(engine.evaluate(cases) for engine in self.engines)
        if not all(report.passed for report in reports):
            failed = [report.engine for report in reports if not report.passed]
            raise ValueError(f"evaluation gate failed: {failed}")
        return reports
