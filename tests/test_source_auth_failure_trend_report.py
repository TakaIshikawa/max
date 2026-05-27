from __future__ import annotations

import json

from max.exports import build_source_auth_failure_trend_report as exported_builder
from max.exports.source_auth_failure_trend_report import (
    KIND,
    SCHEMA_VERSION,
    build_source_auth_failure_trend_report,
    render_source_auth_failure_trend_report_json,
    render_source_auth_failure_trend_report_markdown,
)


def test_source_auth_failure_trend_report_aggregates_by_source_and_day() -> None:
    records = [
        {"source": "github", "adapter": "issues", "credential_scope": "oauth", "timestamp": "2026-05-25T10:00:00Z", "error_code": "401", "failure_count": 2, "recovered": True},
        {"source": "github", "adapter": "issues", "credential_scope": "oauth", "day": "2026-05-25", "error_code": "401", "failure_count": "3", "recovery_status": "resolved"},
        {"source": "slack", "adapter": "messages", "credential_scope": "bot", "day": "2026-05-26", "error_code": "invalid_token", "failure_count": 4},
    ]

    report = build_source_auth_failure_trend_report(records, metadata={"env": "test"})

    assert report == build_source_auth_failure_trend_report(records, metadata={"env": "test"})
    assert exported_builder(records)["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["metadata"] == {"env": "test"}
    assert report["summary"]["failure_count"] == 9
    assert report["summary"]["affected_source_count"] == 2
    assert report["summary"]["recovered_count"] == 5
    assert report["summary"]["unresolved_count"] == 4
    assert report["failure_rows"][0]["failure_count"] == 5
    assert [row["source"] for row in report["top_affected_sources"]] == ["github", "slack"]

    assert json.loads(render_source_auth_failure_trend_report_json(report))["summary"]["failure_count"] == 9
    markdown = render_source_auth_failure_trend_report_markdown(report)
    assert "## Top Affected Sources" in markdown
    assert "github: 5 failures" in markdown
