from __future__ import annotations

import json

from max.api import feedback_outcome_freshness_status_to_json


def test_feedback_outcome_freshness_status_reports_stale_and_missing_segments() -> None:
    report = json.loads(feedback_outcome_freshness_status_to_json({"as_of": "2026-06-01T12:00:00Z", "threshold_hours": 24, "segments": [{"profile": "p1", "reviewer": "r1", "last_outcome_at": "2026-06-01T11:00:00Z"}, {"profile": "p2", "reviewer": "r2", "last_outcome_at": "2026-05-29T11:00:00Z"}, {"profile": "p3", "reviewer": "r3"}]}))
    assert report["overall_status"] == "critical"
    assert [row["profile"] for row in report["stale_segments"]] == ["p2", "p3"]
    assert [row["profile"] for row in report["missing_outcome_blockers"]] == ["p3"]
