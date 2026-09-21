from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptCacheEntry:
    key: str
    model_id: str
    token_count: int


class PromptCacheIndex:
    """Privacy-safe LRU metadata index; backend tensor caches remain backend-owned."""

    def __init__(self, capacity: int = 128) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._entries: OrderedDict[str, PromptCacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key_for(model_id: str, prompt: str) -> str:
        value = f"{model_id}\0{prompt}".encode()
        return hashlib.sha256(value).hexdigest()

    def lookup(self, model_id: str, prompt: str) -> PromptCacheEntry | None:
        key = self.key_for(model_id, prompt)
        with self._lock:
            entry = self._entries.get(key)
            if entry:
                self._entries.move_to_end(key)
            return entry

    def record(self, model_id: str, prompt: str, token_count: int) -> PromptCacheEntry:
        key = self.key_for(model_id, prompt)
        entry = PromptCacheEntry(key, model_id, token_count)
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
        return entry

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
