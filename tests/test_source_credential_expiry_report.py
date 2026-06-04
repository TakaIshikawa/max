from __future__ import annotations

import json

from max.exports.source_credential_expiry_report import (
    build_source_credential_expiry_report,
    generate_source_credential_expiry_report,
    render_source_credential_expiry_report_json,
    render_source_credential_expiry_report_markdown,
)


def test_source_credential_expiry_report_derives_statuses_and_actions() -> None:
    report = build_source_credential_expiry_report(
        [
            {"source": "GitHub", "credential_id": "gh", "expires_at": "2026-05-31T00:00:00Z", "owner": "sec", "rotation_runbook": "rotate GitHub app"},
            {"adapter": "Slack", "credential_id": "slack", "days_until_expiry": 5},
            {"provider": "Zendesk", "credential_id": "zd", "days_until_expiry": 30, "owner": "support"},
        ],
        generated_at="2026-06-04T00:00:00+00:00",
        rotation_due_days=14,
    )

    assert report["schema_version"] == "max.source_credential_expiry_report.v1"
    assert report["kind"] == "max.source_credential_expiry_report"
    assert report["summary"]["credential_count"] == 3
    assert report["summary"]["expired_count"] == 1
    assert report["summary"]["rotation_due_count"] == 1
    assert report["summary"]["valid_count"] == 1
    assert report["summary"]["missing_owner_count"] == 1
    assert report["summary"]["total_source_count"] == 3
    assert report["summary"]["earliest_expiry_at"] == "2026-05-31T00:00:00+00:00"
    assert [row["status"] for row in report["credential_rows"]] == ["expired", "rotation_due", "valid"]
    assert report["credential_rows"][0]["days_until_expiry"] == -4
    assert "GitHub / gh: rotate GitHub app" in report["rotation_actions"]
    assert report["rotation_action_rows"][0]["action"] == "rotate expired credential"
    assert report["owner_summary"] == [{"owner": "sec", "count": 1}, {"owner": "support", "count": 1}, {"owner": "unassigned", "count": 1}]
    assert report["source_totals"][0]["count"] == 1


def test_source_credential_expiry_report_main_markdown_and_generate_alias() -> None:
    report = generate_source_credential_expiry_report(
        [
            {"source": "github", "credential_id": "gh-1", "expires_at": "2026-05-31T00:00:00Z", "owner": "platform"},
            {"source": "slack", "credential_id": "sl-1", "days_until_expiry": 7, "rotation_runbook": "runbook"},
            {"provider": "zendesk", "credential_id": "zd-1", "days_until_expiry": 60, "owner": "support"},
        ],
        generated_at="2026-06-01T00:00:00+00:00",
    )

    markdown = render_source_credential_expiry_report_markdown(report)

    assert "github / gh-1: rotate expired credential" in markdown
    assert json.loads(render_source_credential_expiry_report_json(report))["summary"]["credential_count"] == 3


def test_source_credential_expiry_report_no_action_empty_state() -> None:
    report = build_source_credential_expiry_report([{"source": "github", "days_until_expiry": 30}], rotation_due_days=14)
    markdown = render_source_credential_expiry_report_markdown(report)

    assert "No credential rotation actions required" in markdown
    assert "No credential rotation actions are due." in markdown
