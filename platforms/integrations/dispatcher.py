from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from platforms.integrations.outbox import IntegrationOutbox, OutboxMessage


@dataclass(frozen=True)
class DispatchResult:
    delivered: int
    failed: int
    dead_lettered: int


class OutboxDispatcher:
    def __init__(
        self,
        outbox: IntegrationOutbox,
        handlers: Mapping[str, Callable[[dict[str, Any], str], None]],
    ) -> None:
        self.outbox = outbox
        self.handlers = dict(handlers)

    def run_once(self, limit: int = 100) -> DispatchResult:
        delivered = failed = dead_lettered = 0
        for message in self.outbox.pending(limit):
            handler = self.handlers.get(message.destination)
            if handler is None:
                self.outbox.failed(message.message_id, "destination has no registered handler", 5)
                dead_lettered += 1
                continue
            try:
                handler(message.payload, message.idempotency_key)
                self.outbox.delivered(message.message_id)
                delivered += 1
            except (RuntimeError, ValueError) as exc:
                attempts = message.attempts + 1
                self.outbox.failed(message.message_id, type(exc).__name__, attempts)
                if attempts >= 5:
                    dead_lettered += 1
                else:
                    failed += 1
        return DispatchResult(delivered, failed, dead_lettered)


def delivery_headers(message: OutboxMessage) -> dict[str, str]:
    return {
        "Idempotency-Key": message.idempotency_key,
        "X-OpenModelOps-Message-ID": message.message_id,
    }
