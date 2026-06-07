from __future__ import annotations

import json

from max.api import feedback_weight_impact_status_to_json


def test_feedback_weight_impact_status_reports_largest_delta() -> None:
    data = json.loads(feedback_weight_impact_status_to_json({"material_delta_threshold": 0.2, "weights": [{"profile": "clinical", "dimension": "traceability", "previous_weight": 1.0, "current_weight": 1.1}, {"profile": "aero", "dimension": "safety", "weight_delta": -0.35}]}))

    assert data["status"] == "warning"
    assert data["profile_count"] == 2
    assert data["dimension_count"] == 2
    assert data["largest_delta"] == 0.35
    assert data["affected_profile"] == "aero"
    assert data["affected_dimension"] == "safety"
    assert data["threshold"] == 0.2


def test_feedback_weight_impact_status_empty_is_ok() -> None:
    data = json.loads(feedback_weight_impact_status_to_json({}))

    assert data["status"] == "ok"
    assert data["profile_count"] == 0
    assert data["largest_delta"] == 0.0
