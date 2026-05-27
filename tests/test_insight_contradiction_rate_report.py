from __future__ import annotations

import json

from max.exports import build_insight_contradiction_rate_report
from max.exports.insight_contradiction_rate_report import render_insight_contradiction_rate_report_json, render_insight_contradiction_rate_report_markdown


def test_insight_contradiction_rate_groups_and_flags() -> None:
    report = build_insight_contradiction_rate_report(
        [
            {"profile": "Core", "domain": "Search", "insight_id": "i2", "evidence_labels": ["positive", "negative"]},
            {"profile": "Core", "domain": "Search", "insight_id": "i1", "source_roles": ["supporting"]},
        ],
        high_risk_threshold=0.5,
    )

    row = report["groups"][0]
    assert row["contradiction_rate"] == 0.5
    assert row["top_contradictory_insight_ids"] == ["i2"]
    assert row["high_risk"] is True


def test_insight_contradiction_rate_renderers() -> None:
    report = build_insight_contradiction_rate_report([{"evidence_labels": ["pro", "con"]}])

    assert json.loads(render_insight_contradiction_rate_report_json(report))["summary"]["flagged_group_count"] == 1
    assert "high-risk" in render_insight_contradiction_rate_report_markdown(report)
