from __future__ import annotations

import json

from max.exports import build_insight_to_unit_conversion_funnel_report
from max.exports.insight_to_unit_conversion_funnel_report import (
    render_insight_to_unit_conversion_funnel_report_json,
    render_insight_to_unit_conversion_funnel_report_markdown,
)


def test_insight_to_unit_conversion_funnel_groups_and_sorts() -> None:
    rows = build_insight_to_unit_conversion_funnel_report(
        [
            {"profile": "Beta", "domain": "Ops", "stage": "insight", "count": 4},
            {"profile": "Beta", "domain": "Ops", "stage": "candidate_unit", "count": 3},
            {"profile": "Beta", "domain": "Ops", "stage": "evaluated_unit", "count": 2},
            {"profile": "Beta", "domain": "Ops", "stage": "approved_unit", "count": 1},
            {"profile": "Beta", "domain": "Ops", "stage": "spec_generated", "count": 1},
            {"profile": "Alpha", "domain": "Risk", "status": "spec", "count": 2},
        ]
    )

    assert [(row["profile"], row["domain"]) for row in rows] == [("Alpha", "Risk"), ("Beta", "Ops")]
    assert rows[1]["insight_count"] == 11
    assert rows[1]["spec_generated_count"] == 1
    assert rows[1]["conversion_rate"] == 0.0909
    assert rows[1]["dropoff_stage"] == "insight"
    assert "triage" in rows[1]["recommended_action"]


def test_insight_to_unit_conversion_funnel_renderers() -> None:
    rows = build_insight_to_unit_conversion_funnel_report([{"profile": "Core", "domain": "Search", "stage": "spec_generated"}])

    assert json.loads(render_insight_to_unit_conversion_funnel_report_json(rows))[0]["conversion_rate"] == 1.0
    markdown = render_insight_to_unit_conversion_funnel_report_markdown(rows)
    assert "| Profile | Domain |" in markdown
    assert "| Core | Search |" in markdown
