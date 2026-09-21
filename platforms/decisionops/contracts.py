from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionType(StrEnum):
    CHOICE = "choice"
    SCORE = "score"
    PROBABILITY = "probability"


class QuestionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,119}$")
    version: str = Field(min_length=1, max_length=40)
    decision_type: DecisionType
    description: str = Field(min_length=10, max_length=2000)
    owner: str = Field(min_length=1, max_length=120)
    required_state: list[str] = Field(min_length=1, max_length=100)
    options: list[str] = Field(default_factory=list, max_length=100)
    score_levels: list[str] = Field(default_factory=list, max_length=100)
    minimum_score: float = 0
    maximum_score: float = 1
    confidence_threshold: float = Field(default=0.8, ge=0, le=1)
    cacheable: bool = False
    risk_tier: str = Field(default="standard", pattern=r"^(standard|high|critical)$")

    @model_validator(mode="after")
    def validate_type_configuration(self) -> QuestionDefinition:
        if self.decision_type == DecisionType.CHOICE and len(self.options) < 2:
            raise ValueError("choice questions require at least two options")
        if self.decision_type != DecisionType.CHOICE and self.options:
            raise ValueError("only choice questions may define options")
        if self.decision_type == DecisionType.SCORE and len(self.score_levels) < 2:
            raise ValueError("score questions require at least two ordered score_levels")
        if self.decision_type != DecisionType.SCORE and self.score_levels:
            raise ValueError("only score questions may define score_levels")
        if self.decision_type == DecisionType.SCORE and self.minimum_score >= self.maximum_score:
            raise ValueError("score questions require minimum_score below maximum_score")
        if self.risk_tier == "critical" and self.cacheable:
            raise ValueError("critical decisions cannot be cached")
        return self

    @property
    def digest(self) -> str:
        value = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


class DecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | float
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=2000)


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    trace_id: str
    provider: str
    provider_revision: str
    question_id: str
    question_version: str
    question_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    policy_version: str
    state_schema_version: str
    state_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    output: DecisionOutput
    disposition: str = Field(pattern=r"^(accepted|fallback|human_review)$")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


def state_digest(state: dict[str, Any]) -> str:
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
