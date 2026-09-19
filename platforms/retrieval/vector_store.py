from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class VectorStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    score: float
    text: str
    metadata: dict


class QdrantStore:
    def __init__(self, base_url: str, collection: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.api_key = api_key

    def search(self, vector: list[float], tenant: str, limit: int = 8) -> list[SearchResult]:
        if not tenant:
            raise ValueError("tenant filter is mandatory")
        payload = {
            "vector": vector,
            "limit": min(max(limit, 1), 50),
            "with_payload": True,
            "filter": {"must": [{"key": "tenant", "match": {"value": tenant}}]},
        }
        request = urllib.request.Request(
            f"{self.base_url}/collections/{self.collection}/points/search",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **({"api-key": self.api_key} if self.api_key else {})},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                results = json.loads(response.read()).get("result", [])
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise VectorStoreError(f"vector search failed: {type(exc).__name__}") from exc
        return [
            SearchResult(
                str(item["id"]), float(item["score"]), item.get("payload", {}).get("text", ""), item.get("payload", {})
            )
            for item in results
        ]
