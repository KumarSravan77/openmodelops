from __future__ import annotations

from dataclasses import dataclass

from .contracts import Verdict


@dataclass(frozen=True)
class CalibrationCase:
    case_id: str
    human_pass: bool
    judge_verdict: Verdict


@dataclass(frozen=True)
class CalibrationReport:
    cases: int
    accuracy: float
    false_pass_rate: float
    false_fail_rate: float
    cohen_kappa: float


def calibrate(cases: list[CalibrationCase]) -> CalibrationReport:
    if len(cases) < 2:
        raise ValueError("calibration requires at least two human-labelled cases")
    if any(case.judge_verdict == Verdict.REVIEW for case in cases):
        raise ValueError("human-review verdicts must be resolved before binary calibration")
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
    )
