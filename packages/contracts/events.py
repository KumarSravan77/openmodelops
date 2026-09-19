from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class FactoryEvent:
    event_type: str
    source: str
    tenant: str
    subject: str
    data: dict[str, Any]
    schema_version: str = "1.0"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z]+(?:\.[a-z0-9_-]+)+", self.event_type):
            raise ValueError("event_type must be a namespaced lowercase identifier")
        if not self.source or not self.tenant or not self.subject:
            raise ValueError("source, tenant and subject are required")
        if not re.fullmatch(r"[0-9a-f]{32}", self.trace_id):
            raise ValueError("trace_id must contain 32 lowercase hexadecimal characters")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone aware")

    @property
    def idempotency_key(self) -> str:
        canonical = json.dumps(
            {
                "event_type": self.event_type,
                "source": self.source,
                "tenant": self.tenant,
                "subject": self.subject,
                "data": self.data,
                "schema_version": self.schema_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def envelope(self) -> dict[str, Any]:
        return {
            "specversion": "1.0",
            "id": self.event_id,
            "type": self.event_type,
            "source": self.source,
            "subject": self.subject,
            "time": self.occurred_at.isoformat(),
            "datacontenttype": "application/json",
            "dataschema": f"openmodelops://contracts/{self.event_type}/{self.schema_version}",
            "tenant": self.tenant,
            "trace_id": self.trace_id,
            "idempotency_key": self.idempotency_key,
            "data": self.data,
        }
