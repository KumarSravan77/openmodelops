"""Exercise the three repositories' real contracts with synthetic observations."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
OPENMODELOPS = DEMO_DIR.parents[1]
WORKSPACE = OPENMODELOPS.parent


def invoke(python: str, root: Path, module: str, payload: dict) -> dict:
    env = {**os.environ, "PYTHONPATH": str(root)}
    process = subprocess.run(
        [python, "-m", module], cwd=root, env=env, input=json.dumps(payload),
        capture_output=True, text=True, check=True, timeout=30,
    )
    return json.loads(process.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fire-drill-python", default=sys.executable)
    parser.add_argument("--openmodelops-python", default=sys.executable)
    parser.add_argument("--aria-python", default=sys.executable)
    args = parser.parse_args()

    plan = json.loads((DEMO_DIR / "plan.json").read_text())
    snapshot = json.loads((DEMO_DIR / "snapshot.json").read_text())
    observation = json.loads((DEMO_DIR / "observation.json").read_text())
    envelope = invoke(
        args.fire_drill_python, WORKSPACE / "fire-drill-chaos-engineering",
        "fire_drill.streaming_integration",
        {"plan": plan, "snapshot": snapshot, "observation": observation,
         "experiment_id": "drill-demo-001"},
    )
    assessed = invoke(
        args.openmodelops_python, OPENMODELOPS,
        "platforms.streaming.fire_drill_cli", envelope,
    )
    investigated = invoke(
        args.aria_python, WORKSPACE / "aria-github-update",
        "server.integrations.fire_drill_cli", assessed["aria_request"],
    )
    if not (
        envelope["experiment_id"] == assessed["experiment_id"] == investigated["experiment_id"]
        and envelope["plan_digest"] == assessed["plan_digest"] == investigated["plan_digest"]
        and assessed["assessment"]["evidence_digest"] == investigated["evidence_digest"]
        and investigated["automatic_remediation"] is False
    ):
        raise RuntimeError("cross-repository evidence chain validation failed")

    print(json.dumps({
        "mode": "synthetic-contract-demo",
        "status": "passed",
        "experiment_id": investigated["experiment_id"],
        "plan_digest": investigated["plan_digest"],
        "evidence_digest": investigated["evidence_digest"],
        "finding_codes": [item["code"] for item in investigated["findings"]],
        "fire_drill_report": investigated["fire_drill_report"],
        "slo": investigated["slo"],
        "kafka_agent_available": investigated["investigation"]["available"],
        "decision": investigated["decision"],
        "qualification_verdict": investigated["qualification_verdict"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
