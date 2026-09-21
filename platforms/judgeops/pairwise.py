from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PairwiseDecision:
    winner: str
    rationale: str


class PairwiseComparator(Protocol):
    def compare(self, question: str, first_id: str, first: str, second_id: str, second: str) -> PairwiseDecision: ...


@dataclass(frozen=True)
class OrderBiasReport:
    stable: bool
    winner: str
    forward: PairwiseDecision
    reversed: PairwiseDecision


def test_order_bias(comparator: PairwiseComparator, question: str, candidate_a: str, candidate_b: str) -> OrderBiasReport:
    forward = comparator.compare(question, "a", candidate_a, "b", candidate_b)
    reversed_result = comparator.compare(question, "b", candidate_b, "a", candidate_a)
    valid = {"a", "b", "tie"}
    if forward.winner not in valid or reversed_result.winner not in valid:
        raise ValueError("pairwise comparator returned an invalid winner")
    stable = forward.winner == reversed_result.winner
    return OrderBiasReport(stable, forward.winner if stable else "unstable", forward, reversed_result)
