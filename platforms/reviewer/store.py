from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .domain import InlineComment, PullRequestReview, ReviewSummary, SecurityFinding


class ReviewStore:
    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS pull_reviews (review_key TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )

    def save(self, review: PullRequestReview) -> None:
        payload = {
            "owner": review.owner,
            "repository": review.repository,
            "pull_number": review.pull_number,
            "head_sha": review.head_sha,
            "base_branch": review.base_branch,
            "from_fork": review.from_fork,
            "eligible_at_open": review.eligible_at_open,
            "changed_paths": list(review.changed_paths),
            "summaries": [item.__dict__ for item in review.summaries],
            "inline_comments": [item.__dict__ for item in review.inline_comments],
            "security_findings": [item.__dict__ for item in review.security_findings],
            "fetched_at": review.fetched_at.isoformat() if review.fetched_at else None,
            "approvals": {str(key): value for key, value in review.approvals.items()},
        }
        self._connection.execute(
            "INSERT INTO pull_reviews(review_key, payload) VALUES (?, ?) "
            "ON CONFLICT(review_key) DO UPDATE SET payload = excluded.payload",
            (review.key, json.dumps(payload, separators=(",", ":"))),
        )
        self._connection.commit()

    def get(self, owner: str, repository: str, pull_number: int) -> PullRequestReview | None:
        key = f"{owner}/{repository}#{pull_number}"
        row = self._connection.execute("SELECT payload FROM pull_reviews WHERE review_key = ?", (key,)).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        return PullRequestReview(
            owner=data["owner"],
            repository=data["repository"],
            pull_number=data["pull_number"],
            head_sha=data["head_sha"],
            base_branch=data["base_branch"],
            from_fork=data["from_fork"],
            eligible_at_open=data["eligible_at_open"],
            changed_paths=tuple(data.get("changed_paths", [])),
            summaries=tuple(ReviewSummary(**item) for item in data.get("summaries", [])),
            inline_comments=tuple(InlineComment(**item) for item in data.get("inline_comments", [])),
            security_findings=tuple(SecurityFinding(**item) for item in data.get("security_findings", [])),
            fetched_at=datetime.fromisoformat(data["fetched_at"]) if data.get("fetched_at") else None,
            approvals={int(key): value for key, value in data.get("approvals", {}).items()},
        )
