from __future__ import annotations

import json

from max.exports import build_source_adapter_error_budget_report_export
from max.exports.source_adapter_error_budget_report import (
    render_source_adapter_error_budget_report_json,
    render_source_adapter_error_budget_report_markdown,
)


def test_source_adapter_error_budget_report_sorts_and_summarizes_actions() -> None:
    report = build_source_adapter_error_budget_report_export(
        [
            {"adapter": "rss", "source": "GitHub", "allowed_errors": 3, "actual_errors": 5, "owner": "security"},
            {"adapter": "api", "source": "Slack", "allowed_errors": 10, "consumed_errors": 2},
            {"adapter": "feed", "source": "Zendesk", "allowed_errors": 4, "actual_errors": 4},
        ]
    )

    assert report["schema_version"] == "max.source_adapter_error_budget_report.v1"
    assert report["kind"] == "max.source_adapter_error_budget_report"
    assert report["summary"]["breached_count"] == 1
    assert [row["adapter"] for row in report["adapter_rows"]] == ["rss", "feed", "api"]
    assert report["breached_adapters"][0]["recommended_action"] == "pause ingestion and repair adapter failures"
    assert "GitHub" in render_source_adapter_error_budget_report_markdown(report)
    assert json.loads(render_source_adapter_error_budget_report_json(report))["kind"] == "max.source_adapter_error_budget_report"


def test_source_adapter_error_budget_report_empty_markdown() -> None:
    markdown = render_source_adapter_error_budget_report_markdown(build_source_adapter_error_budget_report_export([]))

    assert "No source adapter error budget records supplied" in markdown
    assert "No adapter error budget records supplied." in markdown
