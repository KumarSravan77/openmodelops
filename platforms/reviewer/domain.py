from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ReviewDecision(str, Enum):
    PENDING = "pending"
    READY = "ready"
    CHANGES_REQUESTED = "changes_requested"
    SKIPPED_FORK = "skipped_fork"


@dataclass(frozen=True)
class ReviewSummary:
    review_id: int
    reviewer: str
    state: str
    body: str
    url: str


@dataclass(frozen=True)
class InlineComment:
    comment_id: int
    reviewer: str
    path: str
    line: int | None
    body: str
    url: str


@dataclass(frozen=True)
class SecurityFinding:
    source: str
    alert_id: str
    severity: str
    path: str
    summary: str
    url: str


@dataclass
class PullRequestReview:
    owner: str
    repository: str
    pull_number: int
    head_sha: str
    base_branch: str
    from_fork: bool
    eligible_at_open: bool
    changed_paths: tuple[str, ...] = ()
    summaries: tuple[ReviewSummary, ...] = ()
    inline_comments: tuple[InlineComment, ...] = ()
    security_findings: tuple[SecurityFinding, ...] = ()
    fetched_at: datetime | None = None
    approvals: dict[int, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.owner}/{self.repository}#{self.pull_number}"

    def record_findings(
        self,
        summaries: tuple[ReviewSummary, ...],
        comments: tuple[InlineComment, ...],
        security_findings: tuple[SecurityFinding, ...] = (),
    ) -> None:
        self.summaries = summaries
        self.inline_comments = comments
        self.security_findings = security_findings
        self.fetched_at = datetime.now(UTC)

    def decision(self, reviewer_login: str, request_changes: bool) -> ReviewDecision:
        if not self.eligible_at_open:
            return ReviewDecision.SKIPPED_FORK
        reviews = [review for review in self.summaries if review.reviewer == reviewer_login]
        if not reviews:
            return ReviewDecision.PENDING
        latest = max(reviews, key=lambda review: review.review_id)
        if request_changes and latest.state.upper() == "CHANGES_REQUESTED":
            return ReviewDecision.CHANGES_REQUESTED
        if latest.state.upper() not in {"APPROVED", "COMMENTED"}:
            return ReviewDecision.PENDING
        return ReviewDecision.READY

    def approve_suggestion(self, comment_id: int, actor: str) -> None:
        if comment_id not in {comment.comment_id for comment in self.inline_comments}:
            raise ValueError("review comment does not exist in the fetched report")
        if not actor.strip():
            raise ValueError("approval actor is required")
        self.approvals[comment_id] = actor

    def require_approved_suggestion(self, comment_id: int) -> str:
        actor = self.approvals.get(comment_id)
        if actor is None:
            raise PermissionError("explicit approval is required before applying a suggestion")
        return actor
