from __future__ import annotations

import json
from types import SimpleNamespace

from max.exports import build_evaluation_override_frequency_report
from max.exports.evaluation_override_frequency_report import render_evaluation_override_frequency_report_json, render_evaluation_override_frequency_report_markdown


def test_evaluation_override_frequency_handles_dicts_and_objects() -> None:
    report = build_evaluation_override_frequency_report(
        [
            {"profile": "Core", "timestamp": "2026-05-27T00:00:00Z", "recommendation": "approve", "reviewer_outcome": "reject", "dimension": "risk"},
            SimpleNamespace(profile="Core", recommendation="approve", reviewer_outcome="approve", dimension="value"),
        ],
        override_threshold=0.5,
    )

    assert [row["period"] for row in report["rows"]] == ["2026-05", "unbucketed"]
    assert report["rows"][0]["override_rate"] == 1.0
    assert report["rows"][0]["top_overridden_dimensions"] == ["risk"]
    assert report["summary"]["flagged_recommendation_count"] == 1


def test_evaluation_override_frequency_renderers() -> None:
    report = build_evaluation_override_frequency_report([{"recommendation": "a", "reviewer_outcome": "b"}])

    assert json.loads(render_evaluation_override_frequency_report_json(report))["rows"][0]["flagged"] is True
    assert "| Profile | Period |" in render_evaluation_override_frequency_report_markdown(report)
