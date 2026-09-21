from __future__ import annotations

from dataclasses import dataclass

from .contracts import JudgeSample, Rubric
from .ensemble import EnsembleJudge


@dataclass(frozen=True)
class ShadowComparison:
    sample_id: str
    active_verdict: str
    candidate_verdict: str
    agreed: bool
    candidate_confidence: float
    candidate_error: str | None = None


@dataclass(frozen=True)
class ShadowReport:
    comparisons: tuple[ShadowComparison, ...]
    agreement_rate: float


class ShadowEvaluator:
    """Evaluates a candidate without allowing its result to control production."""

    def __init__(self, active: EnsembleJudge, candidate: EnsembleJudge) -> None:
        self.active = active
        self.candidate = candidate

    def run(self, samples: list[JudgeSample], rubric: Rubric) -> ShadowReport:
        if not samples:
            raise ValueError("shadow evaluation requires samples")
        comparisons = []
        for sample in samples:
            active = self.active.evaluate(sample, rubric)
            try:
                candidate = self.candidate.evaluate(sample, rubric)
            except Exception as exc:  # noqa: BLE001 - a shadow provider failure is evidence, never production control
                comparisons.append(
                    ShadowComparison(
                        sample.sample_id,
                        active.verdict.value,
                        "provider_error",
                        False,
                        0,
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            comparisons.append(
                ShadowComparison(
                    sample.sample_id,
                    active.verdict.value,
                    candidate.verdict.value,
                    active.verdict == candidate.verdict,
                    candidate.confidence,
                    None,
                )
            )
        agreement = sum(item.agreed for item in comparisons) / len(comparisons)
        return ShadowReport(tuple(comparisons), round(agreement, 6))
