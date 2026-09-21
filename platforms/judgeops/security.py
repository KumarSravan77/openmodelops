from __future__ import annotations

import re

from .contracts import JudgeSample

_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore (all|any|the|previous) (instructions|rubric|criteria)",
        r"system (prompt|message|instructions)",
        r"return (a |the )?(perfect|passing|maximum) score",
        r"you are now (the )?(judge|evaluator|system)",
        r"override (the )?(judge|evaluation|rubric)",
    )
)


def detect_judge_injection(sample: JudgeSample) -> tuple[str, ...]:
    untrusted = "\n".join([sample.question, sample.candidate_answer, *sample.contexts])
    return tuple(pattern.pattern for pattern in _INJECTION_PATTERNS if pattern.search(untrusted))
