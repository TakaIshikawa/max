from __future__ import annotations

import json

from max.api.buildable_unit_evaluation_readiness import buildable_unit_evaluation_readiness_to_json


def test_buildable_unit_evaluation_readiness_reports_missing_fields() -> None:
    parsed = json.loads(
        buildable_unit_evaluation_readiness_to_json(
            {
                "units": [
                    {"id": "ready", "profile": "p", "problem_present": True, "solution_present": True, "stack_present": True, "evidence_count": 2, "evaluation_score": "0.8"},
                    {"id": "evidence", "profile": "p", "problem_present": True, "solution_present": True, "stack_present": True},
                    {"id": "blocked", "profile": "q", "solution_present": True, "stack_present": True, "evidence_count": 1},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.buildable_unit_evaluation_readiness.v1"
    assert [row["unit_id"] for row in parsed["buildable_units"]] == ["blocked", "evidence", "ready"]
    assert parsed["summary"]["ready_count"] == 1
    assert parsed["summary"]["blocked_count"] == 1
    assert parsed["summary"]["needs_evidence_count"] == 1
    assert parsed["blockers"][0]["missing_fields"] == ["problem"]


def test_buildable_unit_evaluation_readiness_aliases_and_metadata() -> None:
    parsed = json.loads(buildable_unit_evaluation_readiness_to_json({"buildable_units": [{"unit_id": "u", "has_problem": "true", "has_solution": "true", "has_stack": "true", "evidence": [{}], "score": "bad"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["buildable_units"][0]["status"] == "ready"
    assert parsed["summary"]["average_evaluation_score"] == 0.0
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
