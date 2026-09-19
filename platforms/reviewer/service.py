from __future__ import annotations

from .config import ReviewAgentConfig
from .domain import PullRequestReview
from .github import GitHubReviewClient
from .store import ReviewStore


class ReviewService:
    def __init__(self, config: ReviewAgentConfig, store: ReviewStore, github: GitHubReviewClient) -> None:
        self.config = config
        self.store = store
        self.github = github

    def open_pull_request(
        self,
        owner: str,
        repository: str,
        pull_number: int,
        head_sha: str,
        base_branch: str,
        from_fork: bool,
        changed_paths: tuple[str, ...] = (),
    ) -> PullRequestReview:
        existing = self.store.get(owner, repository, pull_number)
        if existing is not None:
            return existing
        eligible = base_branch == self.config.target_branch and (not from_fork or self.config.fork_support)
        review = PullRequestReview(
            owner,
            repository,
            pull_number,
            head_sha,
            base_branch,
            from_fork,
            eligible,
            changed_paths,
        )
        self.store.save(review)
        return review

    def refresh_report(self, owner: str, repository: str, pull_number: int) -> PullRequestReview:
        review = self._required(owner, repository, pull_number)
        if not review.eligible_at_open:
            return review
        report = self.github.fetch_report(owner, repository, pull_number)
        security = ()
        if self.config.security_alerts_enabled:
            scopes = {
                check.scope for check in self.config.pr_checks if "security-scanner" in check.name.lower()
            }
            scope = "repo" if "repo" in scopes else "diff"
            security = self.github.fetch_security_findings(
                owner, repository, changed_paths=set(review.changed_paths), scope=scope
            )
        review.record_findings(report.summaries, report.comments, security)
        self.store.save(review)
        return review

    def approve_suggestion(
        self, owner: str, repository: str, pull_number: int, comment_id: int, actor: str
    ) -> PullRequestReview:
        review = self._required(owner, repository, pull_number)
        review.approve_suggestion(comment_id, actor)
        self.store.save(review)
        return review

    def authorize_apply(self, owner: str, repository: str, pull_number: int, comment_id: int) -> dict[str, str | int]:
        review = self._required(owner, repository, pull_number)
        actor = review.require_approved_suggestion(comment_id)
        return {"status": "authorized", "comment_id": comment_id, "approved_by": actor}

    def _required(self, owner: str, repository: str, pull_number: int) -> PullRequestReview:
        review = self.store.get(owner, repository, pull_number)
        if review is None:
            raise KeyError("pull request was not latched at open time")
        return review
