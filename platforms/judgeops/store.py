from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from .contracts import Verdict
from .ensemble import EnsembleResult


class JudgeStore:
    """Durable, content-minimizing audit and human-review store."""

    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS judge_evaluations (
                evaluation_id TEXT PRIMARY KEY,
                sample_id TEXT NOT NULL,
                sample_digest TEXT NOT NULL,
                rubric_id TEXT NOT NULL,
                rubric_digest TEXT NOT NULL,
                verdict TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS judge_reviews (
                evaluation_id TEXT PRIMARY KEY REFERENCES judge_evaluations(evaluation_id),
                status TEXT NOT NULL CHECK(status IN ('pending', 'resolved')),
                human_verdict TEXT,
                reviewer TEXT,
                reason TEXT,
                resolved_at TEXT
            );
            """
        )

    def record(self, result: EnsembleResult, queue_review: bool | None = None) -> str:
        evaluation_id = str(uuid.uuid4())
        first = result.judge_results[0]
        payload = {
            "scores": result.scores,
            "weighted_score": result.weighted_score,
            "confidence": result.confidence,
            "maximum_disagreement": result.maximum_disagreement,
            "reason": result.reason,
            "judges": [item.model_dump(mode="json") for item in result.judge_results],
        }
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT INTO judge_evaluations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evaluation_id,
                    result.sample_id,
                    first.sample_digest,
                    first.rubric_id,
                    first.rubric_digest,
                    result.verdict.value,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    datetime.now(UTC).isoformat(),
                ),
            )
            if queue_review if queue_review is not None else result.verdict == Verdict.REVIEW:
                self.connection.execute(
                    "INSERT INTO judge_reviews(evaluation_id, status) VALUES (?, 'pending')", (evaluation_id,)
                )
        return evaluation_id

    def pending_reviews(self, limit: int = 100) -> list[dict]:
        rows = self.connection.execute(
            """SELECT e.evaluation_id, e.sample_id, e.sample_digest, e.rubric_id,
                      e.verdict, e.created_at
               FROM judge_evaluations e JOIN judge_reviews r USING(evaluation_id)
               WHERE r.status = 'pending' ORDER BY e.created_at LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def resolve(self, evaluation_id: str, reviewer: str, verdict: Verdict, reason: str) -> dict:
        if verdict == Verdict.REVIEW:
            raise ValueError("a human review must resolve to pass or fail")
        if not reviewer.strip() or not reason.strip():
            raise ValueError("reviewer and reason are required")
        with self.lock, self.connection:
            cursor = self.connection.execute(
                """UPDATE judge_reviews SET status = 'resolved', human_verdict = ?, reviewer = ?,
                          reason = ?, resolved_at = ?
                   WHERE evaluation_id = ? AND status = 'pending'""",
                (verdict.value, reviewer, reason, datetime.now(UTC).isoformat(), evaluation_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("pending review not found")
        return {
            "evaluation_id": evaluation_id,
            "status": "resolved",
            "human_verdict": verdict.value,
            "reviewer": reviewer,
            "reason": reason,
        }

    def resolved_calibration_rows(self) -> list[dict]:
        rows = self.connection.execute(
            """SELECT e.evaluation_id AS case_id, e.verdict AS judge_verdict,
                      r.human_verdict, json_extract(e.result_json, '$.confidence') AS confidence
               FROM judge_evaluations e JOIN judge_reviews r USING(evaluation_id)
               WHERE r.status = 'resolved'"""
        ).fetchall()
        return [dict(row) for row in rows]
