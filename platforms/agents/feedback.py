from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class Feedback:
    trace_id: str
    score: int
    category: str
    comment: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if self.score not in {-1, 1}:
            raise ValueError("feedback score must be -1 or 1")
        if self.category not in {"correctness", "safety", "tool", "retrieval", "latency", "other"}:
            raise ValueError("unsupported feedback category")


class FeedbackStore:
    def __init__(self) -> None:
        self._items: list[Feedback] = []

    def add(self, feedback: Feedback) -> None:
        self._items.append(feedback)

    def evaluation_candidates(self) -> list[Feedback]:
        """Feedback is queued for curation; it never changes production directly."""
        return [item for item in self._items if item.score < 0]
