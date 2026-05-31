from __future__ import annotations

import json

from max.api.publisher_channel_error_rate_status import publisher_channel_error_rate_status_to_json


def test_publisher_channel_error_rate_status_healthy() -> None:
    parsed = json.loads(publisher_channel_error_rate_status_to_json({"channels": [{"channel_id": "slack", "attempt_count": 100, "error_count": 1}]}))

    assert parsed["summary"]["status"] == "healthy"


def test_publisher_channel_error_rate_status_degraded_and_critical() -> None:
    parsed = json.loads(publisher_channel_error_rate_status_to_json({"channels": [{"channel_id": "email", "attempt_count": 100, "error_count": 6}, {"channel_id": "slack", "attempt_count": 10, "error_count": 3}]}))

    assert parsed["summary"]["status"] == "critical"
    assert [row["status"] for row in parsed["channels"]] == ["critical", "degraded"]


def test_publisher_channel_error_rate_status_zero_attempt_safe() -> None:
    parsed = json.loads(publisher_channel_error_rate_status_to_json({"channels": [{"channel_id": "empty", "attempt_count": 0, "error_count": 10}]}))

    assert parsed["channels"][0]["error_rate"] == 0.0
    assert parsed["channels"][0]["status"] == "healthy"


def test_publisher_channel_error_rate_status_mixed_channel_error_codes() -> None:
    parsed = json.loads(publisher_channel_error_rate_status_to_json({"channels": [], "errors": [{"code": "429", "count": 2, "channel": "a"}, {"code": "429", "count": 3, "channel": "b"}, {"code": "500", "channel": "a"}]}))

    assert parsed["top_error_codes"][0] == {"code": "429", "count": 5, "sample_channel_ids": ["a", "b"]}
