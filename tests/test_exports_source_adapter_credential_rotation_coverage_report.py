from __future__ import annotations

import json

from max.exports.source_adapter_credential_rotation_coverage_report import (
    build_source_adapter_credential_rotation_coverage_report,
    render_source_adapter_credential_rotation_coverage_report_json,
    render_source_adapter_credential_rotation_coverage_report_markdown,
)


def test_credential_rotation_report_sorts_by_severity_and_identity() -> None:
    report = build_source_adapter_credential_rotation_coverage_report(
        [
            {"source": "GitHub", "adapter": "issues", "credential_type": "oauth", "rotated_at": "2026-05-01", "rotation_interval_days": 90, "owner": "DevEx"},
            {"source": "Datadog", "adapter": "metrics", "credential_type": "api_key", "rotated_at": "2026-03-01", "rotation_interval_days": 60},
            {"source": "Slack", "adapter": "messages", "credential_type": "bot_token", "next_rotation_due_at": "2026-06-05", "rotation_interval_days": 30},
            {"source": "Jira", "adapter": "tickets", "credential_type": "oauth", "missing_policy": True},
            {"source": "Asana", "adapter": "tasks", "credential_type": "token", "rotated_at": "not-a-date", "rotation_interval_days": 30},
            "malformed",
            None,
        ],
        generated_at="2026-06-01T00:00:00+00:00",
    )

    assert [row["rotation_status"] for row in report["coverage_rows"]] == ["overdue", "due_soon", "missing_policy", "unknown", "covered"]
    assert [row["source"] for row in report["coverage_rows"]] == ["Datadog", "Slack", "Jira", "Asana", "GitHub"]
    assert report["summary"] == {
        "adapter_credential_count": 5,
        "covered_count": 1,
        "overdue_count": 1,
        "due_soon_count": 1,
        "missing_policy_count": 1,
        "unknown_count": 1,
    }
    assert report["coverage_rows"][0]["days_until_due"] == -32


def test_credential_rotation_renderers_are_deterministic() -> None:
    report = build_source_adapter_credential_rotation_coverage_report(
        [{"source": "Slack", "adapter": "messages", "credential_type": "bot_token", "next_rotation_due_at": "2026-06-05", "rotation_interval_days": 30}],
        generated_at="2026-06-01",
    )

    rendered = render_source_adapter_credential_rotation_coverage_report_json(report)
    assert rendered.endswith("\n")
    assert json.loads(rendered)["summary"]["due_soon_count"] == 1
    assert "Slack / messages / bot_token: due_soon" in render_source_adapter_credential_rotation_coverage_report_markdown(report)
