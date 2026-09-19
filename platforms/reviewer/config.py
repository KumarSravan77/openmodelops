from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PRCheck:
    name: str
    scope: str = "diff"

    def __post_init__(self) -> None:
        if self.scope not in {"diff", "repo"}:
            raise ValueError("PR check scope must be diff or repo")


@dataclass(frozen=True)
class ReviewAgentConfig:
    target_branch: str = "main"
    fork_support: bool = False
    review_request_changes: bool = True
    reviewer_login: str = "beacode[bot]"
    pr_checks: tuple[PRCheck, ...] = field(default_factory=tuple)

    @property
    def security_alerts_enabled(self) -> bool:
        return any("security-scanner" in check.name.lower() for check in self.pr_checks)

    @classmethod
    def load(cls, path: str | Path) -> ReviewAgentConfig:
        payload = yaml.safe_load(Path(path).read_text()) or {}
        config = payload.get("beacode")
        if not isinstance(config, dict):
            raise TypeError("configuration must contain a top-level beacode mapping")
        checks = tuple(
            PRCheck(name=str(item["name"]), scope=str(item.get("scope", "diff")))
            for item in config.get("pr_checks", [])
        )
        return cls(
            target_branch=str(config.get("target_branch", "main")),
            fork_support=bool(config.get("fork_support", False)),
            review_request_changes=bool(config.get("review_request_changes", True)),
            reviewer_login=str(config.get("reviewer_login", "beacode[bot]")),
            pr_checks=checks,
        )
