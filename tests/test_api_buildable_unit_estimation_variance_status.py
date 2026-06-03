from __future__ import annotations

import json

from max.api.buildable_unit_estimation_variance_status import buildable_unit_estimation_variance_status_to_json


def test_buildable_unit_estimation_variance_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(buildable_unit_estimation_variance_status_to_json({"units": {"u1": {"title": "A", "estimated_effort_points": 2, "actual_effort_points": 6}, "u2": {"estimated_effort_points": 4, "observed_effort_points": 6}, "u3": {"estimated_effort_points": 4, "actual_effort_points": 4}}}, warning_ratio=1.5, critical_ratio=2.5))

    assert [row["unit_id"] for row in report["unit_rows"]] == ["u1", "u2", "u3"]
    assert [row["status"] for row in report["unit_rows"]] == ["critical", "warning", "ok"]
    assert report["unit_rows"][0]["variance_direction"] == "underestimated"


def test_buildable_unit_estimation_variance_status_handles_zero_estimates_and_missing_actuals() -> None:
    report = json.loads(buildable_unit_estimation_variance_status_to_json({"units": [{"unit_id": "zero", "estimated_effort_points": 0, "actual_effort_points": 3}, {"unit_id": "missing", "estimated_effort_points": 3}]}))

    assert [row["status"] for row in report["unit_rows"]] == ["insufficient_data", "insufficient_data"]
    assert report["summary"]["insufficient_data_units"] == 2
