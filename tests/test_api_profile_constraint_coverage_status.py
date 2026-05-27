from __future__ import annotations

import json

from max.api import profile_constraint_coverage_status_to_json


def test_profile_constraint_coverage_status_flags_undercovered_profiles() -> None:
    report = json.loads(profile_constraint_coverage_status_to_json({"profiles": [{"profile": "ops", "required_constraints": ["sla", "cost"], "satisfied_constraints": ["sla"]}, {"profile": "growth", "required_constraints": ["viral"], "satisfied_constraints": ["viral"]}]}))

    assert [row["profile"] for row in report["rows"]] == ["ops", "growth"]
    assert report["rows"][0]["coverage_ratio"] == 0.5
    assert report["undercovered_profiles"][0]["missing_constraints"] == ["cost"]
    assert report["summary"]["required_constraint_count"] == 3
