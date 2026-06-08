from __future__ import annotations

import json

from max.api.spec_acceptance_criteria_completeness_status import spec_acceptance_criteria_completeness_status_to_json


def test_spec_acceptance_criteria_completeness_status_complete() -> None:
    report = json.loads(spec_acceptance_criteria_completeness_status_to_json({"specs": [{"spec_id": "s1", "unit_id": "u1", "required_criteria_count": 2, "present_criteria_count": 2}]}))

    assert report["specs"][0]["completeness_ratio"] == 1.0
    assert report["specs"][0]["status"] == "complete"


def test_spec_acceptance_criteria_completeness_status_partial_and_empty_criteria() -> None:
    report = json.loads(spec_acceptance_criteria_completeness_status_to_json({"specs": [{"spec_id": "partial", "required_criteria_count": 4, "present_criteria_count": 2, "missing_categories": ["security", "ops"]}, {"spec_id": "empty", "required_criteria_count": 2, "criteria": []}]}))

    assert [row["spec_id"] for row in report["specs"]] == ["empty", "partial"]
    assert report["specs"][1]["missing_categories"] == ["security", "ops"]


def test_spec_acceptance_criteria_completeness_status_multiple_specs() -> None:
    report = json.loads(spec_acceptance_criteria_completeness_status_to_json({"specs": [{"spec_id": "b", "required_criteria_count": 1, "present_criteria_count": 1}, {"spec_id": "a", "required_criteria_count": 1, "present_criteria_count": 0}]}))

    assert [row["spec_id"] for row in report["specs"]] == ["a", "b"]
