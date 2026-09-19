from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from packages.contracts import ModelEndpoint


class ModelProviderError(RuntimeError):
    pass


class HttpTransport(Protocol):
    def post(self, url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict: ...


class UrllibTransport:
    def post(self, url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ModelProviderError(f"model provider request failed: {type(exc).__name__}") from exc


@dataclass
class OllamaModel:
    transport: HttpTransport

    def generate(self, endpoint: ModelEndpoint, system_prompt: str, user_input: str) -> str:
        response = self.transport.post(
            endpoint.base_url.rstrip("/") + "/api/chat",
            {
                "model": endpoint.revision,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
            },
            {},
            endpoint.timeout_seconds,
        )
        try:
            return str(response["message"]["content"])
        except (KeyError, TypeError) as exc:
            raise ModelProviderError("Ollama response did not contain message.content") from exc


@dataclass
class OpenAICompatibleModel:
    transport: HttpTransport
    api_key: str = ""

    def generate(self, endpoint: ModelEndpoint, system_prompt: str, user_input: str) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = self.transport.post(
            endpoint.base_url.rstrip("/") + "/v1/chat/completions",
            {
                "model": endpoint.revision,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                "temperature": 0,
            },
            headers,
            endpoint.timeout_seconds,
        )
        try:
            return str(response["choices"][0]["message"]["content"])
        except (IndexError, KeyError, TypeError) as exc:
            raise ModelProviderError("OpenAI-compatible response did not contain a completion") from exc
