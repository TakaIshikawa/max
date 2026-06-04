from __future__ import annotations

import json

from max.exports.source_adapter_error_budget_report import (
    build_source_adapter_error_budget_report_export,
    render_source_adapter_error_budget_report_json,
    render_source_adapter_error_budget_report_markdown,
)


def test_source_adapter_error_budget_report_sorts_and_summarizes() -> None:
    report = build_source_adapter_error_budget_report_export(
        [
            {"adapter": "rss", "source": "GitHub", "allowed_errors": 3, "actual_errors": 5, "owner": "security"},
            {"adapter": "api", "source": "Slack", "allowed_errors": 10, "consumed_errors": 2},
            {"adapter": "feed", "source": "Zendesk", "allowed_errors": 4, "actual_errors": 4},
        ]
    )

    assert report["kind"] == "max.source_adapter_error_budget_report"
    assert report["summary"]["breached_count"] == 1
    assert [row["adapter"] for row in report["adapter_rows"]] == ["rss", "feed", "api"]
    assert report["breached_adapters"][0]["recommended_action"].startswith("pause")


def test_source_adapter_error_budget_renderers_are_deterministic() -> None:
    report = build_source_adapter_error_budget_report_export([])

    assert json.loads(render_source_adapter_error_budget_report_json(report))["schema_version"] == "max.source_adapter_error_budget_report.v1"
    assert "No adapter error budget records supplied." in render_source_adapter_error_budget_report_markdown(report)
