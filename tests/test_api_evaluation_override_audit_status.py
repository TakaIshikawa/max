from __future__ import annotations

import json

from max.api.evaluation_override_audit_status import evaluation_override_audit_status_to_json


def test_evaluation_override_audit_status_marks_missing_reason_and_stale() -> None:
    report = json.loads(evaluation_override_audit_status_to_json({"audit_age_threshold_hours": 24, "overrides": [{"idea_id": "new", "reviewer": "a", "reason": "market", "age_hours": 2}, {"idea_id": "missing", "reviewer": "b", "reason": "", "age_hours": 10}, {"idea_id": "stale", "reviewer": "c", "reason": "risk", "age_hours": 48}]}))

    assert [row["idea_id"] for row in report["rows"]] == ["stale", "missing", "new"]
    assert report["rows"][0]["audit_required"] is True
    assert report["rows"][1]["reason_present"] is False
    assert report["summary"]["override_count"] == 3
    assert report["summary"]["missing_reason_count"] == 1
    assert report["summary"]["audit_required_count"] == 2
