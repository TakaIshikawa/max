from __future__ import annotations

import json

from max.api import publisher_retry_policy_status_to_json


def test_publisher_retry_policy_status_counts_active_paused_and_exhausted() -> None:
    parsed = json.loads(publisher_retry_policy_status_to_json({"policies": [{"destination": "a", "attempts": 3, "max_attempts": 3, "backoff": "linear"}, {"destination": "b", "paused": True, "max_attempts": 5, "backoff_strategy": "exp"}, {"destination": "c", "max_attempts": 5, "backoff": "exp"}]}))

    assert parsed["schema_version"] == "max.api.publisher_retry_policy_status.v1"
    assert parsed["summary"]["destination_count"] == 3
    assert parsed["summary"]["active_count"] == 1
    assert parsed["summary"]["paused_count"] == 1
    assert parsed["summary"]["exhausted_count"] == 1
