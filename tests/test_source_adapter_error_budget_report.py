from __future__ import annotations

import json

from max.exports import build_source_adapter_error_budget_report_export
from max.exports.source_adapter_error_budget_report import (
    render_source_adapter_error_budget_report_json,
    render_source_adapter_error_budget_report_markdown,
)


def test_source_adapter_error_budget_report_sorts_breaches_and_actions() -> None:
    report = build_source_adapter_error_budget_report_export(
        [
            {"adapter": "github", "allowed_errors": 5, "actual_errors": 8, "owner": "platform"},
            {"adapter": "slack", "allowed_errors": 10, "actual_errors": 2},
        ]
    )

    assert report["schema_version"] == "max.source_adapter_error_budget_report.v1"
    assert report["summary"]["breached_count"] == 1
    assert report["adapter_rows"][0]["adapter"] == "github"
    assert report["breached_adapters"][0]["recommended_action"] == "pause ingestion and repair adapter failures"
    assert "github" in render_source_adapter_error_budget_report_markdown(report)
    assert json.loads(render_source_adapter_error_budget_report_json(report))["kind"] == "max.source_adapter_error_budget_report"


def test_source_adapter_error_budget_report_empty_markdown() -> None:
    assert "No source adapter error budget records supplied" in render_source_adapter_error_budget_report_markdown(build_source_adapter_error_budget_report_export([]))
