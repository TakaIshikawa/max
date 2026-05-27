from __future__ import annotations

import json

from max.exports.source_field_completeness_report import build_source_field_completeness_report, render_source_field_completeness_report_json, render_source_field_completeness_report_markdown


def test_source_field_completeness_report_computes_required_and_optional_status() -> None:
    report = build_source_field_completeness_report(
        [
            {"source": "github", "payload": {"title": "a", "labels": ["bug"]}},
            {"source": "github", "payload": {"title": "", "labels": []}},
        ],
        fields=[{"name": "title", "required": True}, {"name": "labels", "required": False}],
        threshold_percent=75,
    )

    assert [row["field_name"] for row in report["completeness_rows"]] == ["labels", "title"]
    assert [row["status"] for row in report["completeness_rows"]] == ["warning", "blocker"]
    assert report["summary"]["blocker_count"] == 1
    assert json.loads(render_source_field_completeness_report_json(report))["summary"]["warning_count"] == 1
    assert "github title: 50.0% blocker" in render_source_field_completeness_report_markdown(report)
