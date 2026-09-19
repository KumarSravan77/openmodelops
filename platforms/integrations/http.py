from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class IntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class JsonResponse:
    status: int
    body: dict[str, Any] | list[Any]


class JsonHttpClient:
    def __init__(self, timeout_seconds: float = 5, maximum_attempts: int = 3) -> None:
        if timeout_seconds <= 0 or not 1 <= maximum_attempts <= 5:
            raise ValueError("invalid HTTP retry configuration")
        self.timeout_seconds = timeout_seconds
        self.maximum_attempts = maximum_attempts

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        idempotent: bool = True,
    ) -> JsonResponse:
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        attempts = self.maximum_attempts if idempotent else 1
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    content = response.read()
                    parsed = json.loads(content) if content else {}
                    return JsonResponse(response.status, parsed)
            except urllib.error.HTTPError as exc:
                if exc.code < 500 or attempt == attempts - 1:
                    raise IntegrationError(f"integration returned HTTP {exc.code}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt == attempts - 1:
                    raise IntegrationError("integration is unavailable") from exc
            time.sleep(0.05 * (2**attempt))
        raise IntegrationError("integration request failed")
