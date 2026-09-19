from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from platforms.integrations.http import JsonHttpClient, JsonResponse


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        idempotent: bool = True,
    ) -> JsonResponse: ...


@dataclass
class ComponentClient:
    base_url: str
    transport: Transport = field(default_factory=JsonHttpClient)

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("component base URL must use HTTP(S)")
        self.base_url = self.base_url.rstrip("/")


class AriaClient(ComponentClient):
    def investigate(self, incident: dict[str, Any], bearer_token: str) -> dict[str, Any]:
        response = self.transport.request(
            "POST",
            f"{self.base_url}/investigate",
            payload=incident,
            headers={"Authorization": f"Bearer {bearer_token}"},
            idempotent=False,
        )
        return dict(response.body)

    def ready(self) -> bool:
        return self.transport.request("GET", f"{self.base_url}/health").status == 200


class OnCallClient(ComponentClient):
    def incident(self, incident_id: str, operator_token: str) -> dict[str, Any]:
        response = self.transport.request(
            "GET",
            f"{self.base_url}/api/v1/incidents/{incident_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        return dict(response.body)

    def investigate(self, incident_id: str, operator_token: str) -> dict[str, Any]:
        response = self.transport.request(
            "POST",
            f"{self.base_url}/api/v1/incidents/{incident_id}/investigate",
            headers={"Authorization": f"Bearer {operator_token}"},
            idempotent=True,
        )
        return dict(response.body)


class ModelServingClient(ComponentClient):
    def ready(self) -> bool:
        return self.transport.request("GET", f"{self.base_url}/readyz").status == 200


class AgentGatewayClient(ComponentClient):
    def request_tool_call(
        self,
        payload: dict[str, Any],
        principal: str,
        scopes: set[str],
    ) -> dict[str, Any]:
        if not payload.get("idempotency_key"):
            raise ValueError("agent tool calls require an idempotency key")
        response = self.transport.request(
            "POST",
            f"{self.base_url}/v1/tool-calls",
            payload=payload,
            headers={"X-Principal": principal, "X-Scopes": " ".join(sorted(scopes))},
            idempotent=True,
        )
        return dict(response.body)
