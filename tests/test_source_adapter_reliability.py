from __future__ import annotations

import json

from max.exports import build_source_adapter_reliability_report as exported_builder
from max.exports.source_adapter_reliability import (
    KIND,
    SCHEMA_VERSION,
    build_source_adapter_reliability_report,
    render_source_adapter_reliability_json,
    render_source_adapter_reliability_markdown,
)


def test_source_adapter_reliability_normalizes_and_renders() -> None:
    records = [
        {"source": "Github", "status": "completed", "started_at": "2026-05-20T00:00:00", "item_count": "12"},
        {
            "source_name": "Slack",
            "status": "failed",
            "started_at": "2026-05-20T01:00:00",
            "item_count": 3,
            "error": "429 rate limit",
            "circuit_breaker_state": "open",
        },
        {"source": "Slack", "status": "success", "started_at": "2026-05-20T02:00:00", "item_count": 9},
    ]

    report = build_source_adapter_reliability_report(records)

    assert report == build_source_adapter_reliability_report(records)
    assert exported_builder(records) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["run_count"] == 3
    assert report["summary"]["success_count"] == 2
    assert report["summary"]["failure_count"] == 1
    assert report["summary"]["success_rate"] == 0.6667
    assert report["summary"]["average_item_count"] == 8.0
    assert [row["source"] for row in report["per_source"]] == ["Slack", "Github"]
    assert report["failing_sources"][0]["source"] == "Slack"
    assert report["open_circuit_breakers"][0]["source"] == "Slack"
    assert report["recent_errors"][0]["error"] == "429 rate limit"

    markdown = render_source_adapter_reliability_markdown(report)
    assert "- Adapter runs: 3" in markdown
    assert "- Failed runs: 1" in markdown
    assert json.loads(render_source_adapter_reliability_json(report))["kind"] == KIND
    assert render_source_adapter_reliability_json(report).endswith("\n")


def test_source_adapter_reliability_defaults_missing_fields() -> None:
    report = build_source_adapter_reliability_report([{}])

    assert report["summary"]["run_count"] == 1
    assert report["summary"]["success_rate"] == 0.0
    assert report["per_source"][0]["source"] == "Unknown source"
    assert report["per_source"][0]["average_item_count"] == 0.0
    assert report["failing_sources"] == []
    assert report["open_circuit_breakers"] == []
    assert "- No failing sources detected." in render_source_adapter_reliability_markdown(report)
