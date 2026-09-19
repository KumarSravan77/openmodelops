from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platforms.factory.governance import EvidenceStatement


@dataclass(frozen=True)
class EvaluationReport:
    pass_rate: float
    passed: int
    total: int
    regression: bool = False

    @classmethod
    def parse(cls, payload: dict[str, Any]) -> EvaluationReport:
        report = cls(
            pass_rate=float(payload["pass_rate"]),
            passed=int(payload["passed"]),
            total=int(payload["total"]),
            regression=bool(payload.get("comparison", {}).get("regression", False)),
        )
        if report.total < 1 or not 0 <= report.passed <= report.total or not 0 <= report.pass_rate <= 1:
            raise ValueError("invalid evaluation report")
        return report


class EvaluationReportAdapter:
    def __init__(self, minimum_pass_rate: float = 0.95) -> None:
        self.minimum_pass_rate = minimum_pass_rate

    def passed(self, report: EvaluationReport) -> bool:
        return report.pass_rate >= self.minimum_pass_rate and not report.regression

    def evidence(
        self,
        workload_id: str,
        report_uri: str,
        report_digest: str,
        evaluator: str,
    ) -> EvidenceStatement:
        return EvidenceStatement(workload_id, "quality", report_uri, report_digest, evaluator)
