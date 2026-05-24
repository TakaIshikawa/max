from __future__ import annotations

import json

from max.api.feedback_weight_adjustment_preview import feedback_weight_adjustment_preview_to_json


def test_feedback_weight_adjustment_preview_derives_delta_and_summary() -> None:
    parsed = json.loads(
        feedback_weight_adjustment_preview_to_json(
            {
                "adjustments": [
                    {"dimension": "fit", "profile": "p", "current_weight": "0.2", "proposed_weight": "0.4"},
                    {"dimension": "risk", "profile": "p", "current_weight": 0.5, "proposed_weight": 0.2},
                    {"dimension": "cost", "profile": "q", "current_weight": 0.1, "proposed_weight": 0.1},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.feedback_weight_adjustment_preview.v1"
    assert [row["dimension"] for row in parsed["adjustments"]] == ["fit", "risk", "cost"]
    assert parsed["adjustments"][0]["delta"] == 0.2
    assert parsed["summary"]["increased_count"] == 1
    assert parsed["summary"]["decreased_count"] == 1
    assert parsed["summary"]["unchanged_count"] == 1
    assert parsed["summary"]["total_absolute_delta"] == 0.5
    assert [row["dimension"] for row in parsed["high_impact_adjustments"]] == ["fit", "risk"]


def test_feedback_weight_adjustment_preview_aliases_malformed_and_metadata() -> None:
    parsed = json.loads(feedback_weight_adjustment_preview_to_json({"weight_adjustments": [{"dimension": "x", "current": "bad", "proposed": "0.05", "source_outcomes": "approved"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["adjustments"][0]["source_outcomes"] == ["approved"]
    assert parsed["adjustments"][0]["delta"] == 0.05
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
