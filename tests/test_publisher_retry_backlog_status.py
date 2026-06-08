from __future__ import annotations

import json

from max.api import publisher_retry_backlog_status_to_json as exported
from max.api.publisher_retry_backlog_status import publisher_retry_backlog_status_to_json


def test_publisher_retry_backlog_status_handles_empty_queue() -> None:
    report = json.loads(publisher_retry_backlog_status_to_json([], as_of="2026-01-01T00:00:00Z"))

    assert exported is publisher_retry_backlog_status_to_json
    assert report["summary"]["status"] == "healthy"
    assert report["retry_backlog"] == []


def test_publisher_retry_backlog_status_groups_and_computes_due_counts() -> None:
    report = json.loads(
        publisher_retry_backlog_status_to_json(
            [
                {"destination": "slack", "channel": "alerts", "created_at": "2025-12-31T23:00:00Z", "next_retry_at": "2025-12-31T23:59:00Z"},
                {"destination": "slack", "channel": "alerts", "created_at": "2025-12-31T23:30:00Z", "next_retry_at": "2026-01-01T00:30:00Z"},
            ],
            as_of="2026-01-01T00:00:00Z",
        )
    )

    assert report["retry_backlog"][0]["pending_count"] == 2
    assert report["retry_backlog"][0]["oldest_retry_age_minutes"] == 60
    assert report["retry_backlog"][0]["next_retry_due_count"] == 1
    assert report["retry_backlog"][0]["status"] == "delayed"


def test_publisher_retry_backlog_status_marks_exhausted_as_blocked() -> None:
    report = json.loads(publisher_retry_backlog_status_to_json([{"destination": "email", "channel": "digest", "attempts": 3, "max_attempts": 3}], as_of="2026-01-01T00:00:00Z"))

    assert report["retry_backlog"][0]["status"] == "blocked"
    assert report["summary"]["status"] == "blocked"
