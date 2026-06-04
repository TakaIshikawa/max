from __future__ import annotations

import json

from max.api.feedback_learning_weight_saturation_status import feedback_learning_weight_saturation_status_to_json


def test_feedback_learning_weight_saturation_status_bounds_warning_and_sorting() -> None:
    parsed = json.loads(
        feedback_learning_weight_saturation_status_to_json(
            {
                "dimensions": [
                    {"dimension": "middle", "current_weight": 0.5, "min_weight": 0, "max_weight": 1, "adjustment_count": 2},
                    {"dimension": "near", "current_weight": 0.93, "min_weight": 0, "max_weight": 1, "adjustment_count": 3},
                    {"dimension": "bound", "current_weight": 1, "min_weight": 0, "max_weight": 1, "adjustment_count": 4},
                    {},
                ]
            },
            warning_saturation_ratio=0.8,
        )
    )

    assert [row["dimension"] for row in parsed["dimensions"]] == ["bound", "dimension-4", "near", "middle"]
    assert parsed["dimensions"][1]["saturation_ratio"] == 1.0
    assert parsed["dimensions"][2]["status"] == "warning"
    assert parsed["summary"]["saturated_dimension_count"] == 2
    assert parsed["summary"]["total_adjustment_count"] == 9
