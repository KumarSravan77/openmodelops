from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from packages.security.auth import AuthorizationError, Identity, require_roles
from packages.security.fastapi_auth import current_identity

from .config import ReviewAgentConfig
from .github import GitHubReviewClient
from .service import ReviewService
from .store import ReviewStore

app = FastAPI(title="OpenModelOps Review Agent", version="0.1.0")
IdentityDependency = Annotated[Identity, Depends(current_identity)]


class OpenPullRequest(BaseModel):
    owner: str
    repository: str
    pull_number: int = Field(gt=0)
    head_sha: str = Field(min_length=7, max_length=64)
    base_branch: str
    from_fork: bool = False
    changed_paths: tuple[str, ...] = ()


@lru_cache
def service() -> ReviewService:
    config = ReviewAgentConfig.load(os.getenv("REVIEW_AGENT_CONFIG", ".beacode/beacode-config.yaml"))
    return ReviewService(
        config,
        ReviewStore(os.getenv("REVIEW_AGENT_DB", "openmodelops-reviewer.db")),
        GitHubReviewClient(os.getenv("GITHUB_API_URL", "https://api.github.com"), os.getenv("GITHUB_TOKEN", "")),
    )


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    service()
    return {"status": "ready"}


@app.post("/v1/pulls/open", status_code=201)
def open_pull(request: OpenPullRequest, identity: IdentityDependency) -> dict:
    authorize(identity, "review-operator")
    review = service().open_pull_request(**request.model_dump())
    return view(review)


@app.post("/v1/pulls/{owner}/{repository}/{pull_number}/refresh")
def refresh(owner: str, repository: str, pull_number: int, identity: IdentityDependency) -> dict:
    authorize(identity, "review-operator")
    try:
        return view(service().refresh_report(owner, repository, pull_number))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/pulls/{owner}/{repository}/{pull_number}/comments/{comment_id}/approve")
def approve(owner: str, repository: str, pull_number: int, comment_id: int, identity: IdentityDependency) -> dict:
    authorize(identity, "review-approver")
    try:
        return view(service().approve_suggestion(owner, repository, pull_number, comment_id, identity.subject))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/pulls/{owner}/{repository}/{pull_number}/comments/{comment_id}/authorize-apply")
def authorize_apply(owner: str, repository: str, pull_number: int, comment_id: int, identity: IdentityDependency) -> dict:
    authorize(identity, "review-operator")
    try:
        return service().authorize_apply(owner, repository, pull_number, comment_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def view(review) -> dict:
    config = service().config
    return {
        "pull_request": review.key,
        "head_sha": review.head_sha,
        "eligible_at_open": review.eligible_at_open,
        "decision": review.decision(config.reviewer_login, config.review_request_changes).value,
        "report_fetched_at": review.fetched_at,
        "reviews": [item.__dict__ for item in review.summaries],
        "inline_comments": [
            {**item.__dict__, "approved_by": review.approvals.get(item.comment_id)} for item in review.inline_comments
        ],
        "security_findings": [item.__dict__ for item in review.security_findings],
    }


def authorize(identity: Identity, role: str) -> None:
    try:
        require_roles(role)(identity)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail="required role missing") from exc
