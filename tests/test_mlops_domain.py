from pathlib import Path

import pytest

from platforms.mlops.domain import EvaluationPolicy, ModelRun, RunState
from platforms.mlops.store import RunStore

DIGEST = "sha256:" + "a" * 64


def make_run() -> ModelRun:
    return ModelRun("run-1", "fraud-risk", DIGEST, "abc1234", "trainer@example.com")


def test_quality_gate_and_separation_of_duties():
    run = make_run()
    run.transition(RunState.TRAINING, run.owner, "start")
    run.transition(RunState.EVALUATING, run.owner, "training complete")
    assert run.record_evaluation(
        {"auc": 0.93, "fairness_gap": 0.04}, DIGEST, EvaluationPolicy({"auc": 0.90}, {"fairness_gap": 0.05}), run.owner
    )
    with pytest.raises(ValueError, match="cannot approve"):
        run.transition(RunState.APPROVED, run.owner, "looks good")
    run.transition(RunState.APPROVED, "risk-reviewer@example.com", "validation evidence accepted")
    assert run.approver == "risk-reviewer@example.com"


def test_failed_quality_gate_is_terminal():
    run = make_run()
    run.transition(RunState.TRAINING, run.owner, "start")
    run.transition(RunState.EVALUATING, run.owner, "done")
    assert not run.record_evaluation({"auc": 0.7}, DIGEST, EvaluationPolicy({"auc": 0.9}), run.owner)
    assert run.state == RunState.REJECTED
    with pytest.raises(ValueError, match="invalid transition"):
        run.transition(RunState.APPROVED, "reviewer", "override")


def test_store_uses_optimistic_concurrency(tmp_path: Path):
    store = RunStore(str(tmp_path / "runs.db"))
    run = make_run()
    assert store.save(run) == 1
    loaded, revision = store.get(run.run_id)
    loaded.transition(RunState.TRAINING, loaded.owner, "start")
    assert store.save(loaded, revision) == 2
    with pytest.raises(RuntimeError, match="concurrent"):
        store.save(loaded, revision)
