from __future__ import annotations

import json

from max.api.buildable_unit_evaluation_readiness_status import buildable_unit_evaluation_readiness_status_to_json


def test_buildable_unit_evaluation_readiness_status_reports_missing_fields() -> None:
    report = json.loads(
        buildable_unit_evaluation_readiness_status_to_json(
            {
                "buildable_units": [
                    {"unit_id": "ready", "problem": "p", "solution": "s", "target_user": "u", "stack": ["py"], "evidence_ids": ["e"], "profile_id": "prof", "extra": None},
                    {"unit_id": "blocked", "problem": "p", "solution": "", "target_user": "u", "stack": [], "evidence_ids": [], "profile_id": "prof"},
                ]
            },
            warning_blocked_ratio=0.25,
            critical_blocked_ratio=0.75,
        )
    )

    assert report["summary"]["ready_count"] == 1
    assert report["summary"]["blocked_count"] == 1
    assert report["summary"]["severity"] == "warn"
    assert report["summary"]["missing_field_counts"]["solution"] == 1
    assert report["rows"][0]["missing_fields"] == ["solution", "stack", "evidence_ids"]
