from __future__ import annotations

import json

from max.api import prompt_failure_recovery_status_to_json


def test_prompt_failure_recovery_status_reports_recovery_rate() -> None:
    data = json.loads(prompt_failure_recovery_status_to_json({"prompts": [{"prompt": "summarize", "failure_count": 3, "retry_count": 4, "recovered_count": 2}, {"prompt": "rank", "failure_count": 1, "retry_count": 1, "recovered_count": 1}]}))

    assert data["status"] == "warning"
    assert data["failure_count"] == 4
    assert data["retry_count"] == 5
    assert data["recovered_count"] == 3
    assert data["unrecovered_count"] == 1
    assert data["recovery_rate"] == 0.75


def test_prompt_failure_recovery_status_handles_zero_failures_and_retries() -> None:
    data = json.loads(prompt_failure_recovery_status_to_json({"failure_count": 0, "retry_count": 0, "recovered_count": 0}))

    assert data["status"] == "ok"
    assert data["recovery_rate"] == 1.0
    assert data["unrecovered_count"] == 0
