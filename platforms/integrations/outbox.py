from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, insert, select, update

outbox_metadata = MetaData()
outbox_table = Table(
    "integration_outbox",
    outbox_metadata,
    Column("message_id", String(64), primary_key=True),
    Column("destination", String(128), nullable=False),
    Column("idempotency_key", String(64), nullable=False, unique=True),
    Column("payload", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("last_error", String(256), nullable=False),
)


@dataclass(frozen=True)
class OutboxMessage:
    message_id: str
    destination: str
    idempotency_key: str
    payload: dict[str, Any]
    status: str
    attempts: int
    available_at: datetime
    last_error: str = ""


class IntegrationOutbox:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url)
        outbox_metadata.create_all(self.engine)

    def enqueue(self, destination: str, idempotency_key: str, payload: dict[str, Any]) -> str:
        existing = select(outbox_table.c.message_id).where(outbox_table.c.idempotency_key == idempotency_key)
        with self.engine.connect() as connection:
            existing_id = connection.execute(existing).scalar_one_or_none()
        if existing_id:
            return str(existing_id)
        message_id = str(uuid.uuid4())
        with self.engine.begin() as connection:
            connection.execute(
                insert(outbox_table).values(
                    message_id=message_id,
                    destination=destination,
                    idempotency_key=idempotency_key,
                    payload=json.dumps(payload, sort_keys=True),
                    status="pending",
                    attempts=0,
                    available_at=datetime.now(UTC),
                    last_error="",
                )
            )
        return message_id

    def pending(self, limit: int = 100) -> list[OutboxMessage]:
        statement = (
            select(outbox_table)
            .where(outbox_table.c.status == "pending", outbox_table.c.available_at <= datetime.now(UTC))
            .order_by(outbox_table.c.available_at)
            .limit(limit)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [self._message(row) for row in rows]

    def delivered(self, message_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(outbox_table).where(outbox_table.c.message_id == message_id).values(status="delivered")
            )

    def failed(self, message_id: str, error: str, attempts: int) -> None:
        terminal = attempts >= 5
        with self.engine.begin() as connection:
            connection.execute(
                update(outbox_table)
                .where(outbox_table.c.message_id == message_id)
                .values(
                    status="dead-letter" if terminal else "pending",
                    attempts=attempts,
                    available_at=datetime.now(UTC) + timedelta(seconds=min(300, 2**attempts)),
                    last_error=error[:256],
                )
            )

    @staticmethod
    def _message(row: Any) -> OutboxMessage:
        return OutboxMessage(
            message_id=row["message_id"],
            destination=row["destination"],
            idempotency_key=row["idempotency_key"],
            payload=json.loads(row["payload"]),
            status=row["status"],
            attempts=row["attempts"],
            available_at=row["available_at"],
            last_error=row["last_error"],
        )
