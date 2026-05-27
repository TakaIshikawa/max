from __future__ import annotations

import json

from max.api import feedback_weight_drift_status_to_json


def test_feedback_weight_drift_status_computes_weight_deltas() -> None:
    parsed = json.loads(feedback_weight_drift_status_to_json({"threshold": 0.1, "weights": [{"dimension": "quality", "baseline": 0.5, "current": 0.8, "approvals": 3}, {"name": "risk", "baseline_weight": 0.4, "current_weight": 0.42}]}))

    assert parsed["schema_version"] == "max.api.feedback_weight_drift_status.v1"
    assert [row["dimension"] for row in parsed["dimensions"]] == ["quality", "risk"]
    assert parsed["dimensions"][0]["abs_delta"] == 0.3
    assert parsed["summary"]["drifted_dimension_count"] == 1
    assert parsed["summary"]["max_abs_delta"] == 0.3
