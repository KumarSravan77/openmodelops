from __future__ import annotations

from dataclasses import dataclass

from .http import IntegrationError, JsonHttpClient


@dataclass(frozen=True)
class RegisteredVersion:
    name: str
    version: str
    source: str


class MLflowRegistryClient:
    """Small MLflow REST adapter used to synchronize governed model releases."""

    def __init__(self, base_url: str, http: JsonHttpClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = http or JsonHttpClient()

    def register_version(self, name: str, source: str, run_id: str, tags: dict[str, str]) -> RegisteredVersion:
        if not name or not source or not run_id:
            raise ValueError("name, source and run_id are required")
        payload = {
            "name": name,
            "source": source,
            "run_id": run_id,
            "tags": [{"key": key, "value": value} for key, value in sorted(tags.items())],
        }
        response = self.http.request(
            "POST",
            f"{self.base_url}/api/2.0/mlflow/model-versions/create",
            payload=payload,
            idempotent=False,
        )
        model = response.body.get("model_version") if isinstance(response.body, dict) else None
        if not isinstance(model, dict) or not model.get("version"):
            raise IntegrationError("MLflow returned an invalid model version")
        return RegisteredVersion(name=name, version=str(model["version"]), source=source)

    def promote_alias(self, name: str, version: str, alias: str = "champion") -> None:
        self.http.request(
            "POST",
            f"{self.base_url}/api/2.0/mlflow/registered-models/alias",
            payload={"name": name, "version": version, "alias": alias},
        )

    def record_governance(self, name: str, version: str, evidence: dict[str, str]) -> None:
        for key, value in sorted(evidence.items()):
            self.http.request(
                "POST",
                f"{self.base_url}/api/2.0/mlflow/model-versions/set-tag",
                payload={"name": name, "version": version, "key": f"openmodelops.{key}", "value": value},
            )
