from __future__ import annotations

import json

from max.api.synthesis_queue_age_status import synthesis_queue_age_status_to_json


def test_synthesis_queue_age_status_groups_and_marks_stale_batches() -> None:
    report = json.loads(
        synthesis_queue_age_status_to_json(
            {
                "batches": [
                    {"profile": "p", "source": "github", "queued_at": "2026-05-31T00:00:00Z"},
                    {"profile": "p", "source": "github", "queued_at": "2026-05-31T01:30:00Z"},
                    {"profile": "p", "source": "hn", "queued_at": "2026-05-31T01:50:00Z"},
                ]
            },
            now="2026-05-31T02:00:00Z",
            warning_age_seconds=1800,
            critical_age_seconds=5400,
        )
    )

    assert report["rows"][0]["source"] == "github"
    assert report["rows"][0]["queued_count"] == 2
    assert report["rows"][0]["oldest_queued_age_seconds"] == 7200
    assert report["rows"][0]["severity"] == "critical"
    assert report["summary"]["stale_batch_count"] == 2


def test_synthesis_queue_age_status_empty_queue_is_healthy() -> None:
    report = json.loads(synthesis_queue_age_status_to_json({"batches": []}, now="2026-05-31T00:00:00Z"))

    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["total_queued_count"] == 0
