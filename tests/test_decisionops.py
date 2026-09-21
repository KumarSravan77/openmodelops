from __future__ import annotations

from pathlib import Path

import pytest

from platforms.decisionops.contracts import DecisionOutput, QuestionDefinition
from platforms.decisionops.engine import CircuitBreaker, DecisionEngine
from platforms.decisionops.registry import QuestionRegistry


class FixedProvider:
    def __init__(self, provider_id: str, output: DecisionOutput, fail: bool = False) -> None:
        self.provider_id = provider_id
        self.provider_revision = "v1"
        self.output = output
        self.fail = fail
        self.calls = 0

    def decide(self, state, question):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return self.output


def test_question_registry_loads_typed_versioned_questions() -> None:
    registry = QuestionRegistry.from_directory(Path("catalog/questions"))
    route = registry.get("agent.route", "1.0.0")
    remediation = registry.get("remediation.supported", "1.0.0")
    assert route.decision_type == "choice"
    assert remediation.risk_tier == "critical"
    assert remediation.cacheable is False


def test_decision_engine_records_versions_and_state_digest() -> None:
    question = QuestionRegistry.from_directory(Path("catalog/questions")).get("agent.route", "1.0.0")
    primary = FixedProvider(
        "structured-primary",
        DecisionOutput(
            value="kubernetes",
            confidence=0.93,
            probabilities={
                "kubernetes": 0.93,
                "database": 0.01,
                "network": 0.01,
                "application": 0.02,
                "security": 0.01,
                "human": 0.02,
            },
        ),
    )
    fallback = FixedProvider("rules", DecisionOutput(value="human", confidence=1))
    record = DecisionEngine(primary, fallback, "policy-v1", "state-v1").evaluate(
        "trace-1",
        {"signal_type": "pod_crash", "affected_resource": "pod/api", "evidence_summary": "CrashLoopBackOff"},
        question,
    )
    assert record.provider == "structured-primary"
    assert record.disposition == "accepted"
    assert record.question_digest == question.digest
    assert record.state_digest.startswith("sha256:")


def test_provider_failure_uses_validated_fallback_and_opens_circuit() -> None:
    question = QuestionRegistry.from_directory(Path("catalog/questions")).get("agent.route", "1.0.0")
    primary = FixedProvider("unavailable", DecisionOutput(value="kubernetes", confidence=1), fail=True)
    fallback = FixedProvider("rules", DecisionOutput(value="human", confidence=1))
    engine = DecisionEngine(primary, fallback, "policy-v1", "state-v1", circuit_breaker=CircuitBreaker(1, 60))
    state = {"signal_type": "unknown", "affected_resource": "unknown", "evidence_summary": "insufficient"}
    first = engine.evaluate("trace-1", state, question)
    second = engine.evaluate("trace-2", state, question)
    assert first.disposition == second.disposition == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 2


def test_low_confidence_decision_requires_human_review() -> None:
    question = QuestionRegistry.from_directory(Path("catalog/questions")).get("remediation.supported", "1.0.0")
    primary = FixedProvider("primary", DecisionOutput(value=0.55, confidence=0.6))
    fallback = FixedProvider("rules", DecisionOutput(value=0, confidence=1))
    record = DecisionEngine(primary, fallback, "policy-v1", "state-v1").evaluate(
        "trace-1", {"proposal": "restart", "evidence": [], "policy_result": "allowed"}, question
    )
    assert record.disposition == "human_review"


def test_invalid_choice_probabilities_fail_closed_through_fallback() -> None:
    question = QuestionRegistry.from_directory(Path("catalog/questions")).get("agent.route", "1.0.0")
    invalid = FixedProvider("invalid", DecisionOutput(value="kubernetes", confidence=1, probabilities={"kubernetes": 1}))
    fallback = FixedProvider("rules", DecisionOutput(value="human", confidence=1))
    record = DecisionEngine(invalid, fallback, "policy-v1", "state-v1").evaluate(
        "trace-1", {"signal_type": "x", "affected_resource": "y", "evidence_summary": "z"}, question
    )
    assert record.provider == "rules"
    assert record.disposition == "fallback"


def test_negative_choice_probability_fails_closed_through_fallback() -> None:
    question = QuestionRegistry.from_directory(Path("catalog/questions")).get("agent.route", "1.0.0")
    invalid = FixedProvider(
        "invalid",
        DecisionOutput(
            value="kubernetes",
            confidence=1,
            probabilities={
                "kubernetes": 1.1,
                "database": -0.1,
                "network": 0,
                "application": 0,
                "security": 0,
                "human": 0,
            },
        ),
    )
    fallback = FixedProvider("rules", DecisionOutput(value="human", confidence=1))
    record = DecisionEngine(invalid, fallback, "policy-v1", "state-v1").evaluate(
        "trace-1", {"signal_type": "x", "affected_resource": "y", "evidence_summary": "z"}, question
    )
    assert record.provider == "rules"
    assert record.disposition == "fallback"


def test_missing_required_state_is_rejected_before_provider_call() -> None:
    question = QuestionRegistry.from_directory(Path("catalog/questions")).get("agent.route", "1.0.0")
    provider = FixedProvider("primary", DecisionOutput(value="human", confidence=1))
    with pytest.raises(ValueError, match="required fields"):
        DecisionEngine(provider, provider, "policy-v1", "state-v1").evaluate("trace", {}, question)
    assert provider.calls == 0


def test_critical_question_cannot_enable_cache() -> None:
    with pytest.raises(ValueError, match="critical decisions cannot be cached"):
        QuestionDefinition.model_validate(
            {
                "question_id": "critical.test",
                "version": "1",
                "decision_type": "probability",
                "description": "A sufficiently long critical decision description.",
                "owner": "platform",
                "required_state": ["evidence"],
                "risk_tier": "critical",
                "cacheable": True,
            }
        )
