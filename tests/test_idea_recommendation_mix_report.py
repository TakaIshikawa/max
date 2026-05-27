from __future__ import annotations

import json

from max.exports import build_idea_recommendation_mix_report
from max.exports.idea_recommendation_mix_report import render_idea_recommendation_mix_report_json, render_idea_recommendation_mix_report_markdown


def test_idea_recommendation_mix_normalizes_aliases_and_sorts() -> None:
    rows = build_idea_recommendation_mix_report(
        [
            {"profile": "Growth", "evaluator": "auto", "source_mode": "signals", "recommendation": "approved", "count": 3},
            {"profile": "Growth", "evaluator": "auto", "source_mode": "signals", "recommendation": "deny"},
            {"evaluator": "human", "mode": "manual", "recommendation": "hold"},
        ]
    )

    assert rows[0]["profile"] == "unknown-profile"
    assert rows[0]["recommendation_counts"]["defer"] == 1
    assert rows[1]["approval_rate"] == 0.75
    assert rows[1]["rejection_rate"] == 0.25
    assert rows[1]["mix_status"] == "approval_heavy"


def test_idea_recommendation_mix_renderers() -> None:
    rows = build_idea_recommendation_mix_report([{"recommendation": "reject"}])

    assert json.loads(render_idea_recommendation_mix_report_json(rows))[0]["total_count"] == 1
    assert "| Profile | Evaluator |" in render_idea_recommendation_mix_report_markdown(rows)
