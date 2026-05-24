from __future__ import annotations

import json

from max.api import synthesis_batch_backlog_status_to_json


def test_synthesis_batch_backlog_status_empty_is_normal() -> None:
    parsed = json.loads(synthesis_batch_backlog_status_to_json({"batches": []}, as_of="2026-05-24T12:00:00Z"))

    assert parsed["summary"]["status"] == "normal"
    assert parsed["summary"]["batch_count"] == 0


def test_synthesis_batch_backlog_status_derives_backlogged_and_stalled() -> None:
    parsed = json.loads(
        synthesis_batch_backlog_status_to_json(
            {
                "batches": [
                    {"id": "old", "profile": "b", "status": "queued", "queued_at": "2026-05-23T00:00:00Z"},
                    {"id": "mid", "profile": "a", "status": "queued", "queued_at": "2026-05-24T02:00:00Z"},
                    {"id": "fail", "profile": "c", "status": "failed"},
                    {"id": "run", "profile": "a", "status": "running"},
                    {"id": "done", "profile": "a", "status": "completed"},
                ]
            },
            as_of="2026-05-24T12:00:00Z",
        )
    )

    assert parsed["summary"]["status"] == "stalled"
    assert parsed["summary"]["queued_count"] == 2
    assert parsed["summary"]["oldest_queued_age_hours"] == 36
    assert [row["profile"] for row in parsed["profile_totals"]] == ["b", "c", "a"]

