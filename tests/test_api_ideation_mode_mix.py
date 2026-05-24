from __future__ import annotations

import json

from max.api.ideation_mode_mix import (
    KIND,
    SCHEMA_VERSION,
    ideation_mode_mix_to_json,
)


def test_ideation_mode_mix_to_json_summarizes_modes() -> None:
    payload = {
        "schema_version": "max.ideation_mode_mix.v1",
        "kind": "max.ideation_mode_mix",
        "ideation_records": [
            {"mode": "refinement", "generated_count": 10, "evaluated_count": 5, "approved_count": 2, "average_score": 0.7},
            {"mode": "direct", "generated_count": 5, "evaluated_count": 5, "approved_count": 4, "average_score": 0.8},
            {"mode": "cross-domain", "generated_count": 8, "evaluated_count": 4, "approved_count": 1, "average_score": 0.6},
        ],
    }

    output = ideation_mode_mix_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {
        "approval_rate": 50.0,
        "best_performing_mode": "direct",
        "evaluation_rate": 60.87,
        "total_approved": 7,
        "total_evaluated": 14,
        "total_generated": 23,
    }
    assert [row["mode"] for row in parsed["mode_totals"]] == ["cross-domain", "direct", "refinement"]
    assert parsed["mode_totals"][1]["approval_rate"] == 80.0
    assert output == ideation_mode_mix_to_json(payload)


def test_ideation_mode_mix_to_json_preserves_unknown_modes_and_defaults() -> None:
    parsed = json.loads(ideation_mode_mix_to_json({"modes": [{"mode": "serendipity"}, {}]}))

    assert [row["mode"] for row in parsed["mode_totals"]] == ["mode-2", "serendipity"]
    assert parsed["mode_totals"][0]["generated_count"] == 0
    assert parsed["summary"]["best_performing_mode"] == "serendipity"
