from __future__ import annotations

import json

from max.api.evaluation_scorecard_missing_dimension_status import evaluation_scorecard_missing_dimension_status_to_json


def test_evaluation_scorecard_missing_dimension_status_normalizes_and_sorts() -> None:
    parsed = json.loads(
        evaluation_scorecard_missing_dimension_status_to_json(
            {
                "evaluations": [
                    {"evaluation_id": "ok", "expected_dimensions": ["a", "b"], "scored_dimensions": ["a", "b"]},
                    {"evaluation_id": "warn", "expected_dimensions": ["a", "b"], "scored_dimensions": ["a"]},
                    {"evaluation_id": "critical", "expected_dimensions": ["a", "b", "c"], "scored_dimensions": "a"},
                    {"evaluation_id": "empty", "expected_dimensions": [], "scored_dimensions": []},
                ]
            },
            warning_coverage_ratio=0.75,
            critical_coverage_ratio=0.4,
        )
    )

    assert [row["evaluation_id"] for row in parsed["evaluations"]] == ["empty", "critical", "warn", "ok"]
    assert parsed["evaluations"][1]["missing_dimensions"] == ["b", "c"]
    assert parsed["evaluations"][0]["coverage_ratio"] == 0.0
    assert parsed["summary"]["incomplete_scorecard_count"] == 2
