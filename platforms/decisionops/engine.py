from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import DecisionOutput, DecisionRecord, DecisionType, QuestionDefinition, state_digest


class DecisionProvider(Protocol):
    provider_id: str
    provider_revision: str

    def decide(self, state: dict[str, Any], question: QuestionDefinition) -> DecisionOutput: ...


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    reset_seconds: float = 30
    failures: int = 0
    opened_at: float | None = None

    def allow(self) -> bool:
        if self.opened_at is None:
            return True
        if time.monotonic() - self.opened_at >= self.reset_seconds:
            self.failures = 0
            self.opened_at = None
            return True
        return False

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()


class DecisionEngine:
    def __init__(
        self,
        provider: DecisionProvider,
        fallback: DecisionProvider,
        policy_version: str,
        state_schema_version: str,
        cache_capacity: int = 1000,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.provider = provider
        self.fallback = fallback
        self.policy_version = policy_version
        self.state_schema_version = state_schema_version
        self.cache_capacity = cache_capacity
        self.breaker = circuit_breaker or CircuitBreaker()
        self._cache: OrderedDict[str, DecisionOutput] = OrderedDict()

    def evaluate(self, trace_id: str, state: dict[str, Any], question: QuestionDefinition) -> DecisionRecord:
        missing = sorted(set(question.required_state) - set(state))
        if missing:
            raise ValueError(f"state omitted required fields: {missing}")
        digest = state_digest(state)
        key = self._cache_key(digest, question)
        cached = self._cache.get(key) if question.cacheable else None
        used_fallback = False
        if cached is not None:
            output = cached
            self._cache.move_to_end(key)
        elif self.breaker.allow():
            try:
                output = self.provider.decide(state, question)
                self._validate(output, question)
                self.breaker.success()
            except Exception:  # noqa: BLE001 - provider isolation and explicit fallback are the safety boundary
                self.breaker.failure()
                output = self.fallback.decide(state, question)
                self._validate(output, question)
                used_fallback = True
        else:
            output = self.fallback.decide(state, question)
            self._validate(output, question)
            used_fallback = True
        if question.cacheable and cached is None and not used_fallback:
            self._cache[key] = output
            while len(self._cache) > self.cache_capacity:
                self._cache.popitem(last=False)
        disposition = "human_review" if output.confidence < question.confidence_threshold else "fallback" if used_fallback else "accepted"
        provider = self.fallback if used_fallback else self.provider
        return DecisionRecord(
            decision_id=str(uuid.uuid4()),
            trace_id=trace_id,
            provider=provider.provider_id,
            provider_revision=provider.provider_revision,
            question_id=question.question_id,
            question_version=question.version,
            question_digest=question.digest,
            policy_version=self.policy_version,
            state_schema_version=self.state_schema_version,
            state_digest=digest,
            output=output,
            disposition=disposition,
        )

    def _cache_key(self, digest: str, question: QuestionDefinition) -> str:
        return json.dumps(
            [digest, question.digest, self.provider.provider_revision, self.policy_version, self.state_schema_version],
            separators=(",", ":"),
        )

    @staticmethod
    def _validate(output: DecisionOutput, question: QuestionDefinition) -> None:
        if question.decision_type == DecisionType.CHOICE:
            if output.value not in question.options:
                raise ValueError("choice provider returned an unknown option")
            if output.probabilities and set(output.probabilities) != set(question.options):
                raise ValueError("choice probabilities must cover every option exactly")
            if any(probability < 0 or probability > 1 for probability in output.probabilities.values()):
                raise ValueError("choice probabilities must be between zero and one")
            if output.probabilities and abs(sum(output.probabilities.values()) - 1) > 0.001:
                raise ValueError("choice probabilities must sum to one")
        elif not isinstance(output.value, (int, float)):
            raise ValueError("score and probability decisions require numeric values")
        elif question.decision_type == DecisionType.PROBABILITY and not 0 <= float(output.value) <= 1:
            raise ValueError("probability decision must be between zero and one")
        elif question.decision_type == DecisionType.SCORE and not question.minimum_score <= float(output.value) <= question.maximum_score:
            raise ValueError("score decision is outside the registered range")
