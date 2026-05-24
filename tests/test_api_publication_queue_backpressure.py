from __future__ import annotations

import json

from max.api.publication_queue_backpressure import publication_queue_backpressure_to_json


def test_publication_queue_backpressure_derives_status_and_totals() -> None:
    parsed = json.loads(
        publication_queue_backpressure_to_json(
            {
                "destinations": [
                    {"destination": "ok", "pending_count": "2", "inflight_count": 1},
                    {"destination": "slow", "pending_count": "50", "oldest_pending_age_minutes": 10},
                    {"destination": "blocked", "failed_count": "5"},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.publication_queue_backpressure.v1"
    assert [row["destination"] for row in parsed["destinations"]] == ["blocked", "slow", "ok"]
    assert parsed["summary"]["pending_count"] == 52
    assert parsed["summary"]["backlogged_count"] == 1
    assert parsed["summary"]["blocked_count"] == 1
    assert parsed["blocked_destinations"][0]["destination"] == "blocked"


def test_publication_queue_backpressure_aliases_malformed_and_metadata() -> None:
    parsed = json.loads(publication_queue_backpressure_to_json({"publication_destinations": [{"name": "x", "pending": "bad", "rate_limited": "true", "retry_after": "30"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["destinations"][0]["pending_count"] == 0
    assert parsed["destinations"][0]["status"] == "blocked"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
