from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import DecisionOutput, DecisionType, QuestionDefinition


@dataclass
class JevDecisionProvider:
    """Optional TypeSafe JEV adapter; intended for benchmark and shadow use first."""

    client: Any
    provider_id: str = "typesafe-jev"
    provider_revision: str = "early-access"

    def decide(self, state: dict[str, Any], question: QuestionDefinition) -> DecisionOutput:
        try:
            from typesafe_sdk import Choice, Noul, Score
        except ImportError as exc:  # pragma: no cover - optional provider dependency
            raise RuntimeError("install typesafe-sdk to use the JEV provider") from exc

        instructions = question.description
        if question.decision_type == DecisionType.CHOICE:
            typed_question = Choice(instructions=instructions, criteria={option: None for option in question.options})
        elif question.decision_type == DecisionType.SCORE:
            typed_question = Score(instructions=instructions, criteria=question.score_levels)
        else:
            typed_question = Noul(instructions=instructions)

        response = self.client.system_one(state=state, questions={question.question_id: typed_question})
        if question.decision_type == DecisionType.CHOICE:
            answer = response.choices[question.question_id]
            return DecisionOutput(
                value=str(answer.choice),
                probabilities={str(key): float(value) for key, value in answer.probabilities.items()},
                confidence=float(answer.confidence),
                rationale="Typed Choice decision returned by JEV.",
            )
        if question.decision_type == DecisionType.SCORE:
            answer = response.scores[question.question_id]
            return DecisionOutput(
                value=float(answer.score),
                probabilities={str(key): float(value) for key, value in answer.probabilities.items()},
                confidence=float(answer.confidence),
                rationale="Typed Score decision returned by JEV.",
            )
        probability = float(response.nouls[question.question_id].noul)
        return DecisionOutput(
            value=probability,
            confidence=round(abs(probability - 0.5) * 2, 6),
            rationale="Typed Noul probability returned by JEV; confidence is derived distance from 0.5.",
        )
