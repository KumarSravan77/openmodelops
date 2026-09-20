from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from platforms.kubernetes_sre.actions import ActionProposal, ActionType, Approval


class SREStore:
    """Durable local store. Startup fails closed if persistence cannot be opened."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS proposals (
              proposal_id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL,
              status TEXT NOT NULL, approval TEXT
            );
            CREATE TABLE IF NOT EXISTS reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT, cluster TEXT NOT NULL,
              generated_at TEXT NOT NULL, payload TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def save_report(self, report: dict[str, object]) -> None:
        self.connection.execute(
            "INSERT INTO reports(cluster, generated_at, payload) VALUES (?, ?, ?)",
            (report["cluster"], report["generated_at"], json.dumps(report, sort_keys=True)),
        )
        self.connection.commit()

    def save_proposal(self, proposal: ActionProposal) -> None:
        payload = {
            "action": proposal.action.value,
            "cluster": proposal.cluster,
            "namespace": proposal.namespace,
            "resource_name": proposal.resource_name,
            "resource_uid": proposal.resource_uid,
            "resource_version": proposal.resource_version,
            "requested_by": proposal.requested_by,
            "rationale": proposal.rationale,
            "rollback": proposal.rollback,
            "parameters": proposal.parameters,
            "proposal_id": proposal.proposal_id,
            "created_at": proposal.created_at.isoformat(),
        }
        self.connection.execute(
            "INSERT INTO proposals(proposal_id, payload, digest, status) VALUES (?, ?, ?, 'proposed')",
            (proposal.proposal_id, json.dumps(payload, sort_keys=True), proposal.digest),
        )
        self.connection.commit()

    def get_proposal(self, proposal_id: str) -> ActionProposal:
        row = self.connection.execute("SELECT payload FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        payload = json.loads(row[0])
        payload["action"] = ActionType(payload["action"])
        payload["created_at"] = datetime.fromisoformat(payload["created_at"])
        return ActionProposal(**payload)

    def approve(self, approval: Approval) -> None:
        cursor = self.connection.execute(
            "UPDATE proposals SET approval = ?, status = 'approved' WHERE proposal_id = ? AND digest = ? AND status = 'proposed'",
            (json.dumps({"proposal_id": approval.proposal_id, "proposal_digest": approval.proposal_digest,
                         "approved_by": approval.approved_by, "approved_at": approval.approved_at.isoformat(),
                         "expires_at": approval.expires_at.isoformat()}), approval.proposal_id, approval.proposal_digest),
        )
        if cursor.rowcount != 1:
            raise ValueError("proposal is missing, changed, or already approved")
        self.connection.commit()

    def get_approval(self, proposal_id: str) -> Approval:
        row = self.connection.execute("SELECT approval FROM proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
        if row is None or row[0] is None:
            raise KeyError(proposal_id)
        payload = json.loads(row[0])
        payload["approved_at"] = datetime.fromisoformat(payload["approved_at"])
        payload["expires_at"] = datetime.fromisoformat(payload["expires_at"])
        return Approval(**payload)

    def claim_execution(self, proposal_id: str) -> None:
        cursor = self.connection.execute(
            "UPDATE proposals SET status = 'executing' WHERE proposal_id = ? AND status = 'approved'", (proposal_id,)
        )
        if cursor.rowcount != 1:
            raise ValueError("proposal is not approved or execution was already claimed")
        self.connection.commit()

    def finish_execution(self, proposal_id: str, succeeded: bool) -> None:
        status = "executed" if succeeded else "failed"
        self.connection.execute(
            "UPDATE proposals SET status = ? WHERE proposal_id = ? AND status = 'executing'", (status, proposal_id)
        )
        self.connection.commit()
