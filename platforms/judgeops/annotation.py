from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .contracts import Verdict


class AnnotationLedger:
    """Append-only reviewer labels with two-person consensus promotion."""

    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS annotations (
                sample_id TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK(verdict IN ('pass', 'fail')),
                rationale TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(sample_id, reviewer)
            );
            """
        )

    def label(self, sample_id: str, reviewer: str, verdict: Verdict, rationale: str) -> None:
        if verdict == Verdict.REVIEW:
            raise ValueError("reviewers must resolve labels to pass or fail")
        if not sample_id.strip() or not reviewer.strip() or len(rationale.strip()) < 10:
            raise ValueError("sample ID, reviewer and a meaningful rationale are required")
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO annotations(sample_id, reviewer, verdict, rationale) VALUES (?, ?, ?, ?)",
                (sample_id, reviewer, verdict.value, rationale),
            )

    def status(self, sample_id: str) -> dict:
        rows = self.connection.execute(
            "SELECT reviewer, verdict, rationale, created_at FROM annotations WHERE sample_id = ? ORDER BY reviewer",
            (sample_id,),
        ).fetchall()
        labels = [dict(row) for row in rows]
        verdicts = {row["verdict"] for row in rows}
        return {
            "sample_id": sample_id,
            "labels": labels,
            "status": "consensus" if len(labels) >= 2 and len(verdicts) == 1 else "conflict" if len(verdicts) > 1 else "pending",
        }

    def export_consensus(self, candidate_path: Path, output_path: Path) -> dict:
        promoted = []
        pending = 0
        conflicts = 0
        for line in candidate_path.read_text().splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            state = self.status(payload["sample"]["sample_id"])
            if state["status"] == "consensus":
                payload.pop("expected_verdict", None)
                payload["human_verdict"] = state["labels"][0]["verdict"]
                payload["label_source"] = "human"
                payload["label_status"] = "verified"
                payload["reviewers"] = [item["reviewer"] for item in state["labels"]]
                promoted.append(payload)
            elif state["status"] == "conflict":
                conflicts += 1
            else:
                pending += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in promoted))
        return {"promoted": len(promoted), "pending": pending, "conflicts": conflicts}
