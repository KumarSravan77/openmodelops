from __future__ import annotations

import json
import sys

from platforms.streaming.api import FireDrillEnvelope, evaluate_fire_drill


def main() -> None:
    request = FireDrillEnvelope.model_validate(json.load(sys.stdin))
    print(json.dumps(evaluate_fire_drill(request), sort_keys=True))


if __name__ == "__main__":
    main()
