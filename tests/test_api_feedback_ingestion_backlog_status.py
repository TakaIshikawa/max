from __future__ import annotations

import json

from max.api import feedback_ingestion_backlog_status_to_json


def test_feedback_ingestion_backlog_reports_age_label_mix_and_unknowns() -> None:
    report = json.loads(feedback_ingestion_backlog_status_to_json({"events": [{"id": "old", "label": "approval", "queued_at": "2026-05-30T00:00:00Z"}, {"id": "x", "label": "custom", "queued_at": "2026-05-31T00:00:00Z"}]}, now="2026-05-31T12:00:00Z"))

    assert report["summary"] == {"backlog_count": 2, "oldest_age_hours": 36.0, "severity": "critical"}
    assert report["label_mix"] == {"approval": 1, "unknown": 1}
    assert report["events"][0]["event_id"] == "old"


def test_feedback_ingestion_backlog_empty_is_ok() -> None:
    report = json.loads(feedback_ingestion_backlog_status_to_json({}, now="2026-05-31T00:00:00Z"))

    assert report["summary"]["severity"] == "ok"
    assert report["summary"]["backlog_count"] == 0
