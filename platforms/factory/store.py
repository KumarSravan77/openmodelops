from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, insert, select, text, update
from sqlalchemy.engine import Engine

from platforms.factory.domain import (
    SLO,
    FactorySpec,
    FactoryWorkload,
    GateResult,
    GateStatus,
    WorkloadKind,
    WorkloadStage,
)

metadata = MetaData()
workload_table = Table(
    "factory_workloads",
    metadata,
    Column("workload_id", String(64), primary_key=True),
    Column("tenant", String(128), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("document", Text, nullable=False),
)


class ConcurrencyError(RuntimeError):
    pass


class FactoryStore:
    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_engine(database_url)
        metadata.create_all(self.engine)

    def create(self, workload: FactoryWorkload) -> int:
        with self.engine.begin() as connection:
            connection.execute(
                insert(workload_table).values(
                    workload_id=workload.workload_id,
                    tenant=workload.spec.tenant,
                    version=1,
                    document=self._serialize(workload),
                )
            )
        return 1

    def get(self, workload_id: str, tenant: str) -> tuple[FactoryWorkload, int] | None:
        statement = select(workload_table).where(
            workload_table.c.workload_id == workload_id,
            workload_table.c.tenant == tenant,
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return self._deserialize(row["document"]), row["version"]

    def save(self, workload: FactoryWorkload, expected_version: int) -> int:
        statement = (
            update(workload_table)
            .where(
                workload_table.c.workload_id == workload.workload_id,
                workload_table.c.tenant == workload.spec.tenant,
                workload_table.c.version == expected_version,
            )
            .values(version=expected_version + 1, document=self._serialize(workload))
        )
        with self.engine.begin() as connection:
            result = connection.execute(statement)
        if result.rowcount != 1:
            raise ConcurrencyError("workload changed concurrently")
        return expected_version + 1

    def ready(self) -> bool:
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    @staticmethod
    def _serialize(workload: FactoryWorkload) -> str:
        document = {
            "spec": {**asdict(workload.spec), "kind": workload.spec.kind.value},
            "workload_id": workload.workload_id,
            "stage": workload.stage.value,
            "gates": {
                name: {**asdict(result), "status": result.status.value, "measured_at": result.measured_at.isoformat()}
                for name, result in workload.gates.items()
            },
            "approved_by": workload.approved_by,
            "policy_digest": workload.policy_digest,
            "history": workload.history,
        }
        return json.dumps(document, sort_keys=True)

    @staticmethod
    def _deserialize(document: str) -> FactoryWorkload:
        raw = json.loads(document)
        spec_raw = raw["spec"]
        slo = SLO(**spec_raw.pop("slo"))
        kind = WorkloadKind(spec_raw.pop("kind"))
        spec = FactorySpec(**spec_raw, kind=kind, slo=slo)
        workload = FactoryWorkload(
            spec=spec,
            workload_id=raw["workload_id"],
            stage=WorkloadStage(raw["stage"]),
            approved_by=raw["approved_by"],
            policy_digest=raw.get("policy_digest"),
            history=raw["history"],
        )
        workload.gates = {
            name: GateResult(
                gate=value["gate"],
                status=GateStatus(value["status"]),
                evidence=value["evidence"],
                evaluator=value["evaluator"],
                evidence_digest=value.get("evidence_digest", ""),
                signing_key_id=value.get("signing_key_id", ""),
                signature=value.get("signature", ""),
                measured_at=datetime.fromisoformat(value["measured_at"]),
            )
            for name, value in raw["gates"].items()
        }
        return workload
