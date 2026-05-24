from __future__ import annotations

import json

from max.api.evaluation_dimension_drift import evaluation_dimension_drift_to_json


def test_evaluation_dimension_drift_calculates_deltas_and_regressions() -> None:
    parsed = json.loads(
        evaluation_dimension_drift_to_json(
            {
                "drift_threshold": 0.05,
                "regression_threshold": 0.1,
                "dimensions": [
                    {"dimension": "value", "profile": "A", "current": 0.7, "baseline": 0.85},
                    {"dimension": "risk", "profile": "A", "current": 0.9, "baseline": 0.8},
                    {"dimension": "fit", "profile": "B", "current": 0.81, "baseline": 0.8},
                ],
            }
        )
    )

    assert [row["status"] for row in parsed["dimensions"]] == ["regressed", "drifting", "stable"]
    assert parsed["dimensions"][0]["delta"] == -0.15
    assert parsed["affected_profiles"][0] == {"profile": "a", "affected_dimension_count": 2}
    assert parsed["summary"]["status"] == "regressed"


def test_evaluation_dimension_drift_empty_input_is_stable() -> None:
    parsed = json.loads(evaluation_dimension_drift_to_json({}))

    assert parsed["summary"]["status"] == "stable"
    assert parsed["dimensions"] == []
