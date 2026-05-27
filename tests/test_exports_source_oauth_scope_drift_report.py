from __future__ import annotations

import json

from max.exports.source_oauth_scope_drift_report import build_source_oauth_scope_drift_report, render_source_oauth_scope_drift_report_json, render_source_oauth_scope_drift_report_markdown


def test_source_oauth_scope_drift_report_handles_empty_input() -> None:
    report = build_source_oauth_scope_drift_report([])

    assert report["drift_rows"] == []
    assert report["summary"]["integration_count"] == 0
    assert "No OAuth scope drift" in render_source_oauth_scope_drift_report_markdown(report)


def test_source_oauth_scope_drift_report_groups_sorts_and_escalates_missing_scopes() -> None:
    report = build_source_oauth_scope_drift_report(
        [
            {"source": "jira", "integration_id": "prod", "required_scopes": ["read", "write"], "observed_scopes": ["read"], "affected_operation_count": 2, "last_observed_at": "2026-05-27T02:00:00Z"},
            {"source": "github", "integration_id": "prod", "required_scopes": ["repo"], "observed_scopes": ["repo", "admin"], "operation_count": 3, "last_observed_at": "2026-05-27T01:00:00Z"},
            {"source": "jira", "integration_id": "prod", "required_scopes": ["delete"], "observed_scopes": ["read"], "affected_operation_count": 1, "last_observed_at": "2026-05-27T03:00:00Z"},
        ]
    )

    assert [(row["source"], row["integration"]) for row in report["drift_rows"]] == [("jira", "prod"), ("github", "prod")]
    assert report["drift_rows"][0]["missing_scopes"] == ["delete", "write"]
    assert report["drift_rows"][0]["risk_level"] == "critical"
    assert report["drift_rows"][0]["affected_operation_count"] == 3
    assert report["drift_rows"][1]["extra_scopes"] == ["admin"]
    assert report["drift_rows"][1]["risk_level"] == "warning"
    assert report["summary"]["critical_count"] == 1
    assert json.loads(render_source_oauth_scope_drift_report_json(report))["kind"] == report["kind"]
