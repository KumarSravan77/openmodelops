from __future__ import annotations

from dataclasses import dataclass

from .contracts import Verdict


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    human_pass: bool
    judge_verdict: Verdict
    pass_probability: float | None = None


@dataclass(frozen=True)
class CalibrationReport:
    cases: int
    accuracy: float
    false_pass_rate: float
    false_fail_rate: float
    cohen_kappa: float
    precision: float
    recall: float
    brier_score: float | None


@dataclass(frozen=True)
class CalibrationPolicy:
    minimum_cases: int = 50
    minimum_accuracy: float = 0.9
    maximum_false_pass_rate: float = 0.05
    maximum_false_fail_rate: float = 0.1
    minimum_kappa: float = 0.75
    maximum_brier_score: float = 0.12

    def failures(self, report: CalibrationReport) -> tuple[str, ...]:
        failures = []
        if report.cases < self.minimum_cases:
            failures.append("insufficient_cases")
        if report.accuracy < self.minimum_accuracy:
            failures.append("accuracy")
        if report.false_pass_rate > self.maximum_false_pass_rate:
            failures.append("false_pass_rate")
        if report.false_fail_rate > self.maximum_false_fail_rate:
            failures.append("false_fail_rate")
        if report.cohen_kappa < self.minimum_kappa:
            failures.append("cohen_kappa")
        if report.brier_score is None or report.brier_score > self.maximum_brier_score:
            failures.append("brier_score")
        return tuple(failures)

    def qualify(self, report: CalibrationReport) -> None:
        failures = self.failures(report)
        if failures:
            raise ValueError(f"judge calibration gate failed: {list(failures)}")


def calibrate(cases: list[CalibrationCase]) -> CalibrationReport:
    if len(cases) < 2:
        raise ValueError("calibration requires at least two human-labelled cases")
    if any(case.judge_verdict == Verdict.REVIEW for case in cases):
        raise ValueError("human-review verdicts must be resolved before binary calibration")
    probabilities = [case.pass_probability for case in cases]
    if any(value is not None and not 0 <= value <= 1 for value in probabilities):
        raise ValueError("pass probabilities must be between zero and one")
    if any(value is None for value in probabilities) and any(value is not None for value in probabilities):
        raise ValueError("pass probabilities must be supplied for every case or no cases")
    tp = sum(case.human_pass and case.judge_verdict == Verdict.PASS for case in cases)
    tn = sum(not case.human_pass and case.judge_verdict == Verdict.FAIL for case in cases)
    fp = sum(not case.human_pass and case.judge_verdict == Verdict.PASS for case in cases)
    fn = sum(case.human_pass and case.judge_verdict == Verdict.FAIL for case in cases)
    count = len(cases)
    observed = (tp + tn) / count
    human_positive = (tp + fn) / count
    judge_positive = (tp + fp) / count
    expected = human_positive * judge_positive + (1 - human_positive) * (1 - judge_positive)
    kappa = 1.0 if expected == 1 and observed == 1 else (observed - expected) / (1 - expected)
    return CalibrationReport(
        count,
        round(observed, 6),
        round(fp / max(1, fp + tn), 6),
        round(fn / max(1, fn + tp), 6),
        round(kappa, 6),
        round(tp / max(1, tp + fp), 6),
        round(tp / max(1, tp + fn), 6),
        (
            round(
                sum((float(case.pass_probability) - float(case.human_pass)) ** 2 for case in cases) / count,
                6,
            )
            if all(value is not None for value in probabilities)
            else None
        ),
    )
