from __future__ import annotations

import sys
from types import SimpleNamespace

from platforms.decisionops.contracts import DecisionType, QuestionDefinition
from platforms.decisionops.jev import JevDecisionProvider


class FakeChoice:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeNoul(FakeChoice):
    pass


class FakeScore(FakeChoice):
    pass


class FakeClient:
    def system_one(self, state, questions):
        assert state["signal_type"] == "pod_crash"
        assert "agent.route" in questions
        return SimpleNamespace(
            choices={
                "agent.route": SimpleNamespace(
                    choice="kubernetes",
                    probabilities={"kubernetes": 0.9, "human": 0.1},
                    confidence=0.8,
                )
            }
        )


def test_jev_choice_adapter_maps_typed_response(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "typesafe_sdk",
        SimpleNamespace(Choice=FakeChoice, Noul=FakeNoul, Score=FakeScore),
    )
    question = QuestionDefinition(
        question_id="agent.route",
        version="1",
        decision_type=DecisionType.CHOICE,
        description="Select the correct operational specialist for this signal.",
        owner="platform",
        required_state=["signal_type"],
        options=["kubernetes", "human"],
    )
    output = JevDecisionProvider(FakeClient()).decide({"signal_type": "pod_crash"}, question)
    assert output.value == "kubernetes"
    assert output.probabilities == {"kubernetes": 0.9, "human": 0.1}
