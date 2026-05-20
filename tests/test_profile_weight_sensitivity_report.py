from __future__ import annotations

import json

from max.exports.profile_weight_sensitivity_report import (
    KIND,
    build_profile_weight_sensitivity_report,
    render_profile_weight_sensitivity_report_json,
)


def test_profile_weight_sensitivity_report_summarizes_risk() -> None:
    report = build_profile_weight_sensitivity_report(
        [
            {"profile": "growth", "dimension": "reach", "baseline_weight": 0.2, "proposed_weight": 0.5, "affected_idea_count": 10, "average_score_delta": "0.12555", "recommendation_change_count": 4},
            {"profile": "growth", "dimension": "confidence", "baseline_weight": 0.4, "proposed_weight": 0.45, "recommendation_change_count": 1},
            {"profile": "ops", "dimension": "cost", "baseline_weight": 0.3, "proposed_weight": 0.31, "recommendation_change_count": 0},
        ]
    )

    assert report["kind"] == KIND
    assert report["summary"]["dimension_count"] == 3
    assert report["summary"]["largest_weight_delta"] == 0.3
    assert report["dimension_sensitivity"][1]["average_score_delta"] == 0.1255
    assert report["largest_weight_shifts"][0]["dimension"] == "reach"
    assert [row["dimension"] for row in report["recommendation_sensitive_dimensions"]] == ["reach", "confidence"]
    assert report["profile_risk_levels"][0]["risk_level"] == "high"
    assert json.loads(render_profile_weight_sensitivity_report_json(report))["summary"]["high_risk_profile_count"] == 1


def test_profile_weight_sensitivity_report_defaults_missing_fields() -> None:
    report = build_profile_weight_sensitivity_report([{}])

    row = report["dimension_sensitivity"][0]
    assert row["profile"] == "Unassigned profile"
    assert row["dimension"] == "Unknown dimension"
    assert row["weight_delta"] == 0.0
    assert row["risk_level"] == "low"
    assert report["review_actions"] == []
