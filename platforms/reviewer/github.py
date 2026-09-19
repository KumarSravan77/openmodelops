from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from platforms.integrations.http import IntegrationError, JsonHttpClient

from .domain import InlineComment, ReviewSummary, SecurityFinding


@dataclass(frozen=True)
class ReviewReport:
    summaries: tuple[ReviewSummary, ...]
    comments: tuple[InlineComment, ...]


class GitHubReviewClient:
    def __init__(self, base_url: str, token: str, http: JsonHttpClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or JsonHttpClient()
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def fetch_report(self, owner: str, repo: str, pull_number: int) -> ReviewReport:
        root = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        reviews = self._all_pages(f"{root}/reviews")
        comments = self._all_pages(f"{root}/comments")
        return ReviewReport(
            tuple(
                ReviewSummary(
                    review_id=int(item["id"]),
                    reviewer=str(item.get("user", {}).get("login", "unknown")),
                    state=str(item.get("state", "PENDING")),
                    body=str(item.get("body") or ""),
                    url=str(item.get("html_url") or ""),
                )
                for item in reviews
            ),
            tuple(
                InlineComment(
                    comment_id=int(item["id"]),
                    reviewer=str(item.get("user", {}).get("login", "unknown")),
                    path=str(item.get("path") or ""),
                    line=item.get("line") or item.get("original_line"),
                    body=str(item.get("body") or ""),
                    url=str(item.get("html_url") or ""),
                )
                for item in comments
            ),
        )

    def fetch_security_findings(
        self,
        owner: str,
        repo: str,
        *,
        changed_paths: set[str],
        scope: str,
    ) -> tuple[SecurityFinding, ...]:
        if scope not in {"diff", "repo"}:
            raise ValueError("security scope must be diff or repo")
        root = f"{self.base_url}/repos/{owner}/{repo}"
        dependabot = self._all_pages(f"{root}/dependabot/alerts?state=open")
        code_scanning = self._all_pages(f"{root}/code-scanning/alerts?state=open")
        findings = [self._dependabot_finding(item) for item in dependabot]
        findings.extend(self._code_scanning_finding(item) for item in code_scanning)
        if scope == "diff":
            findings = [finding for finding in findings if finding.path in changed_paths]
        return tuple(findings)

    def _all_pages(self, url: str) -> list[dict[str, Any]]:
        separator = "&" if "?" in url else "?"
        output: list[dict[str, Any]] = []
        for page in range(1, 101):
            response = self.http.request(
                "GET", f"{url}{separator}{urlencode({'per_page': 100, 'page': page})}", headers=self.headers
            )
            if not isinstance(response.body, list):
                raise IntegrationError("GitHub API returned an invalid paginated response")
            output.extend(item for item in response.body if isinstance(item, dict))
            if len(response.body) < 100:
                return output
        raise IntegrationError("GitHub API pagination exceeded safety limit")

    @staticmethod
    def _dependabot_finding(item: dict[str, Any]) -> SecurityFinding:
        advisory = item.get("security_advisory") or {}
        dependency = item.get("dependency") or {}
        return SecurityFinding(
            "dependabot",
            str(item.get("number", "unknown")),
            str(advisory.get("severity", "unknown")),
            str(dependency.get("manifest_path", "")),
            str(advisory.get("summary", "Dependency alert")),
            str(item.get("html_url", "")),
        )

    @staticmethod
    def _code_scanning_finding(item: dict[str, Any]) -> SecurityFinding:
        rule = item.get("rule") or {}
        location = item.get("most_recent_instance", {}).get("location", {})
        return SecurityFinding(
            "codeql",
            str(item.get("number", "unknown")),
            str(rule.get("security_severity_level") or rule.get("severity", "unknown")),
            str(location.get("path", "")),
            str(rule.get("description", "Code scanning alert")),
            str(item.get("html_url", "")),
        )
