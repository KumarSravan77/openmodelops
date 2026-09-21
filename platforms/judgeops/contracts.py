from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    REVIEW = "human_review"


class RubricDimension(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    description: str = Field(min_length=10, max_length=1000)
    threshold: float = Field(ge=0, le=1)
    weight: float = Field(gt=0, le=10)


class Rubric(BaseModel):
    rubric_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{2,79}$")
    version: str = Field(min_length=1, max_length=40)
    dimensions: list[RubricDimension] = Field(min_length=1, max_length=20)
    minimum_confidence: float = Field(default=0.7, ge=0, le=1)

    @model_validator(mode="after")
    def dimensions_are_unique(self) -> Rubric:
        names = [dimension.name for dimension in self.dimensions]
        if len(names) != len(set(names)):
            raise ValueError("rubric dimension names must be unique")
        return self

    @property
    def digest(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


class JudgeSample(BaseModel):
    sample_id: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=100_000)
    candidate_answer: str = Field(min_length=1, max_length=200_000)
    reference_answer: str | None = Field(default=None, max_length=200_000)
    contexts: list[str] = Field(default_factory=list, max_length=100)
    expected_tools: list[str] = Field(default_factory=list, max_length=100)
    risk_tier: str = Field(default="standard", pattern=r"^(standard|high|critical)$")

    @property
    def content_digest(self) -> str:
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


class ClaimAssessment(BaseModel):
    claim: str = Field(min_length=1, max_length=2000)
    supported: bool
    evidence: str = Field(default="", max_length=2000)


class JudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    judge_id: str = Field(min_length=1, max_length=160)
    judge_revision: str = Field(min_length=1, max_length=160)
    rubric_id: str
    rubric_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    sample_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    verdict: Verdict
    scores: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=5000)
    claims: list[ClaimAssessment] = Field(default_factory=list, max_length=100)
    injection_detected: bool = False

    @model_validator(mode="after")
    def scores_are_probabilities(self) -> JudgeResult:
        if any(not 0 <= score <= 1 for score in self.scores.values()):
            raise ValueError("judge scores must be between zero and one")
        return self
