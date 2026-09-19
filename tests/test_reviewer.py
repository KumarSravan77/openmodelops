from pathlib import Path

import pytest

from platforms.integrations.http import JsonResponse
from platforms.reviewer.config import PRCheck, ReviewAgentConfig
from platforms.reviewer.domain import InlineComment, ReviewDecision, ReviewSummary, SecurityFinding
from platforms.reviewer.github import GitHubReviewClient, ReviewReport
from platforms.reviewer.service import ReviewService
from platforms.reviewer.store import ReviewStore


class HTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return JsonResponse(200, self.responses.pop(0))


class GitHub:
    def __init__(self, report=None, security=()):
        self.report = report or ReviewReport((), ())
        self.security = security
        self.security_calls = []

    def fetch_report(self, owner, repo, pull_number):
        return self.report

    def fetch_security_findings(self, owner, repo, *, changed_paths, scope):
        self.security_calls.append((changed_paths, scope))
        return self.security


def service(config=None, github=None):
    return ReviewService(config or ReviewAgentConfig(), ReviewStore(":memory:"), github or GitHub())


def test_config_requires_nested_beacode_key(tmp_path: Path):
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("target_branch: main\n")
    with pytest.raises(TypeError, match="top-level beacode"):
        ReviewAgentConfig.load(invalid)


def test_config_parses_security_opt_in_and_scope(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "beacode:\n  target_branch: develop\n  fork_support: true\n  review_request_changes: false\n"
        "  pr_checks:\n    - name: security-scanner-alerts\n      scope: repo\n"
    )
    config = ReviewAgentConfig.load(path)
    assert config.target_branch == "develop"
    assert config.fork_support is True
    assert config.security_alerts_enabled is True
    assert config.pr_checks[0].scope == "repo"


def test_fork_eligibility_is_latched_at_open_time():
    store = ReviewStore(":memory:")
    initial = ReviewService(ReviewAgentConfig(fork_support=False), store, GitHub())
    opened = initial.open_pull_request("org", "repo", 4, "abcdef1", "main", True)
    assert opened.decision("beacode[bot]", True) == ReviewDecision.SKIPPED_FORK

    changed_config = ReviewService(ReviewAgentConfig(fork_support=True), store, GitHub())
    still_skipped = changed_config.open_pull_request("org", "repo", 4, "newsha12", "main", True)
    assert still_skipped.eligible_at_open is False


def test_skipped_fork_never_calls_review_api():
    github = GitHub()
    github.fetch_report = lambda *_: pytest.fail("skipped fork must not call review API")
    review_service = service(ReviewAgentConfig(fork_support=False), github)
    review_service.open_pull_request("org", "repo", 4, "abcdef1", "main", True)
    review = review_service.refresh_report("org", "repo", 4)
    assert review.decision("beacode[bot]", True) == ReviewDecision.SKIPPED_FORK


def test_non_target_branch_is_not_eligible():
    review = service().open_pull_request("org", "repo", 2, "abcdef1", "feature", False)
    assert review.eligible_at_open is False


def test_refresh_fetches_summary_and_inline_comments_before_ready():
    report = ReviewReport(
        (ReviewSummary(10, "beacode[bot]", "APPROVED", "Looks good", "review-url"),),
        (InlineComment(20, "beacode[bot]", "app.py", 7, "Suggestion", "comment-url"),),
    )
    review_service = service(github=GitHub(report))
    before = review_service.open_pull_request("org", "repo", 1, "abcdef1", "main", False)
    assert before.decision("beacode[bot]", True) == ReviewDecision.PENDING
    after = review_service.refresh_report("org", "repo", 1)
    assert after.fetched_at is not None
    assert after.decision("beacode[bot]", True) == ReviewDecision.READY
    assert after.inline_comments[0].path == "app.py"


def test_latest_bot_review_controls_change_request_decision():
    report = ReviewReport(
        (
            ReviewSummary(10, "beacode[bot]", "APPROVED", "", ""),
            ReviewSummary(11, "beacode[bot]", "CHANGES_REQUESTED", "", ""),
        ),
        (),
    )
    review_service = service(github=GitHub(report))
    review_service.open_pull_request("org", "repo", 1, "abcdef1", "main", False)
    review = review_service.refresh_report("org", "repo", 1)
    assert review.decision("beacode[bot]", True) == ReviewDecision.CHANGES_REQUESTED
    assert review.decision("beacode[bot]", False) == ReviewDecision.PENDING


def test_suggestion_requires_explicit_approval_before_authorization():
    report = ReviewReport((), (InlineComment(20, "beacode[bot]", "app.py", 7, "Suggestion", ""),))
    review_service = service(github=GitHub(report))
    review_service.open_pull_request("org", "repo", 1, "abcdef1", "main", False)
    review_service.refresh_report("org", "repo", 1)
    with pytest.raises(PermissionError, match="explicit approval"):
        review_service.authorize_apply("org", "repo", 1, 20)
    review_service.approve_suggestion("org", "repo", 1, 20, "human-reviewer")
    result = review_service.authorize_apply("org", "repo", 1, 20)
    assert result == {"status": "authorized", "comment_id": 20, "approved_by": "human-reviewer"}


def test_unknown_comment_cannot_be_approved():
    review_service = service()
    review_service.open_pull_request("org", "repo", 1, "abcdef1", "main", False)
    with pytest.raises(ValueError, match="does not exist"):
        review_service.approve_suggestion("org", "repo", 1, 999, "human")


def test_security_alerts_are_opt_in_and_diff_scoped():
    finding = SecurityFinding("codeql", "7", "high", "changed.py", "Injection", "url")
    github = GitHub(security=(finding,))
    config = ReviewAgentConfig(pr_checks=(PRCheck("security-scanner-alerts", "diff"),))
    review_service = service(config, github)
    review_service.open_pull_request("org", "repo", 1, "abcdef1", "main", False, ("changed.py",))
    review = review_service.refresh_report("org", "repo", 1)
    assert review.security_findings == (finding,)
    assert github.security_calls == [({"changed.py"}, "diff")]


def test_security_api_is_not_called_without_matching_check():
    github = GitHub()
    review_service = service(ReviewAgentConfig(pr_checks=(PRCheck("unit-tests"),)), github)
    review_service.open_pull_request("org", "repo", 1, "abcdef1", "main", False)
    review_service.refresh_report("org", "repo", 1)
    assert github.security_calls == []


def test_github_client_calls_reviews_and_comments_endpoints_with_pagination():
    http = HTTP(
        [
            [{"id": 1, "user": {"login": "beacode[bot]"}, "state": "APPROVED", "body": "ok"}],
            [{"id": 2, "user": {"login": "beacode[bot]"}, "path": "a.py", "line": 3, "body": "fix"}],
        ]
    )
    report = GitHubReviewClient("https://ghe.example/api/v3", "opaque", http).fetch_report("org", "repo", 9)
    assert len(report.summaries) == 1
    assert len(report.comments) == 1
    assert "/pulls/9/reviews?" in http.calls[0][1]
    assert "/pulls/9/comments?" in http.calls[1][1]
    assert http.calls[0][2]["headers"]["Authorization"] == "Bearer opaque"


def test_security_findings_filter_to_changed_paths():
    http = HTTP(
        [
            [
                {
                    "number": 1,
                    "dependency": {"manifest_path": "requirements.txt"},
                    "security_advisory": {"severity": "high", "summary": "dependency"},
                }
            ],
            [
                {
                    "number": 2,
                    "rule": {"security_severity_level": "critical", "description": "code"},
                    "most_recent_instance": {"location": {"path": "src/app.py"}},
                }
            ],
        ]
    )
    findings = GitHubReviewClient("https://ghe/api/v3", "opaque", http).fetch_security_findings(
        "org", "repo", changed_paths={"src/app.py"}, scope="diff"
    )
    assert [(item.source, item.path) for item in findings] == [("codeql", "src/app.py")]
