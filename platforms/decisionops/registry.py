from __future__ import annotations

from pathlib import Path

import yaml

from .contracts import QuestionDefinition


class QuestionRegistry:
    def __init__(self, questions: list[QuestionDefinition]) -> None:
        keys = [(question.question_id, question.version) for question in questions]
        if len(keys) != len(set(keys)):
            raise ValueError("question IDs and versions must be unique")
        self._questions = {key: question for key, question in zip(keys, questions, strict=True)}

    @classmethod
    def from_directory(cls, path: Path) -> QuestionRegistry:
        questions = []
        for file in sorted(path.glob("*.yaml")):
            payload = yaml.safe_load(file.read_text())
            questions.append(QuestionDefinition.model_validate(payload))
        if not questions:
            raise ValueError("question registry cannot be empty")
        return cls(questions)

    def get(self, question_id: str, version: str) -> QuestionDefinition:
        try:
            return self._questions[(question_id, version)]
        except KeyError as exc:
            raise KeyError(f"unknown question: {question_id}@{version}") from exc
