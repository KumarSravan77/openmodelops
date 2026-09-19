from __future__ import annotations

import json
import sqlite3

from .domain import ModelRun, RunState


class RunStore:
    def __init__(self, path: str = "openmodelops-mlops.db") -> None:
        self.path = path
        self._init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init(self) -> None:
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS model_runs (
                run_id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1
            )""")

    def save(self, run: ModelRun, expected_revision: int | None = None) -> int:
        payload = json.dumps({**run.__dict__, "state": run.state.value}, sort_keys=True)
        with self._connect() as connection:
            row = connection.execute("SELECT revision FROM model_runs WHERE run_id=?", (run.run_id,)).fetchone()
            if row is None:
                if expected_revision not in (None, 0):
                    raise RuntimeError("concurrent update detected")
                connection.execute(
                    "INSERT INTO model_runs(run_id,payload,revision) VALUES(?,?,1)", (run.run_id, payload)
                )
                return 1
            if expected_revision is not None and row["revision"] != expected_revision:
                raise RuntimeError("concurrent update detected")
            revision = row["revision"] + 1
            connection.execute(
                "UPDATE model_runs SET payload=?,revision=? WHERE run_id=?", (payload, revision, run.run_id)
            )
            return revision

    def get(self, run_id: str) -> tuple[ModelRun, int]:
        with self._connect() as connection:
            row = connection.execute("SELECT payload,revision FROM model_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        data = json.loads(row["payload"])
        data["state"] = RunState(data["state"])
        return ModelRun(**data), row["revision"]
