from __future__ import annotations

import json

from max.api import evaluation_dimension_coverage_status_to_json


def test_evaluation_dimension_coverage_status_flags_missing_and_null_dimensions() -> None:
    data = json.loads(evaluation_dimension_coverage_status_to_json({"required_dimensions": ["impact", "confidence"], "evaluations": [{"unit_id": "u1", "dimensions": {"impact": 1, "confidence": None}}, {"unit_id": "u2", "dimensions": {"impact": 1, "confidence": 1}}]}))

    assert data["summary"]["complete_count"] == 1
    assert data["summary"]["missing_dimension_count"] == 1
    assert data["rows"][0]["unit_id"] == "u1"
    assert data["rows"][0]["missing_dimensions"] == ["confidence"]


def test_evaluation_dimension_coverage_status_accepts_items_and_defaults_required_dimensions() -> None:
    data = json.loads(evaluation_dimension_coverage_status_to_json({"items": [{"id": "u", "impact": 1, "confidence": 1, "effort": 1}]}))

    assert data["summary"]["status"] == "complete"
    assert data["rows"][0]["coverage_ratio"] == 1.0
