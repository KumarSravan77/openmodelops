from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelEndpoint:
    name: str
    revision: str
    base_url: str
    protocol: str = "openai-compatible"
    timeout_seconds: int = 60

    def __post_init__(self) -> None:
        if not self.name or not self.revision or not self.base_url.startswith(("http://", "https://")):
            raise ValueError("model endpoint requires a name, revision and HTTP(S) base URL")
        if self.timeout_seconds < 1 or self.timeout_seconds > 600:
            raise ValueError("timeout_seconds must be between 1 and 600")


@dataclass(frozen=True)
class ModelRelease:
    model_name: str
    version: str
    artifact_digest: str
    stage: str

    def __post_init__(self) -> None:
        if self.stage not in {"candidate", "staging", "production", "retired"}:
            raise ValueError(f"unsupported stage: {self.stage}")
        if not self.artifact_digest.startswith("sha256:"):
            raise ValueError("artifact_digest must be content-addressed with sha256")
