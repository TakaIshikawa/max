from __future__ import annotations

import json

from max.api import run_step_retry_status_to_json


def test_run_step_retry_status_flags_exhausted_and_retrying_steps() -> None:
    report = json.loads(run_step_retry_status_to_json({"steps": [{"run_id": "b", "step": "publish", "attempts": 2, "max_attempts": 3}, {"run_id": "a", "step": "fetch", "attempts": 3, "max_attempts": 3}, {"run_id": "c", "step": "score", "attempts": 0, "max_attempts": 3}]}))

    assert [row["run_id"] for row in report["rows"]] == ["a", "b", "c"]
    assert report["retry_blocked_steps"][0]["next_action"] == "escalate"
    assert report["summary"]["status"] == "exhausted"
