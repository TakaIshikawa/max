from __future__ import annotations

import json

from max.api.publisher_retry_dead_letter_status import publisher_retry_dead_letter_status_to_json


def test_publisher_retry_dead_letter_status_groups_destinations() -> None:
    report = json.loads(
        publisher_retry_dead_letter_status_to_json(
            [
                {"destination": "slack", "reason": "timeout", "dead_lettered_at": "2026-01-03T00:00:00Z"},
                {"destination": "slack", "reason": "timeout", "dead_lettered_at": "2026-01-02T00:00:00Z"},
                {"destination": "jira", "dead_lettered_at": "2026-01-01T00:00:00Z"},
            ],
            critical_count=2,
        )
    )

    assert [row["destination"] for row in report["destinations"]] == ["slack", "jira"]
    assert report["destinations"][0]["oldest_dead_lettered_at"] == "2026-01-02T00:00:00Z"
    assert report["destinations"][1]["top_reason"] == "unknown"

