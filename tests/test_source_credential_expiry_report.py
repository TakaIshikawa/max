from __future__ import annotations

import json

from max.exports.source_credential_expiry_report import (
    build_source_credential_expiry_report,
    render_source_credential_expiry_report_json,
    render_source_credential_expiry_report_markdown,
)


def test_source_credential_expiry_report_statuses_and_actions() -> None:
    report = build_source_credential_expiry_report(
        [
            {"source": "github", "credential_id": "gh-1", "expires_at": "2026-05-31T00:00:00Z", "owner": "platform"},
            {"source": "slack", "credential_id": "sl-1", "days_until_expiry": 7, "rotation_runbook": "runbook"},
            {"provider": "zendesk", "credential_id": "zd-1", "days_until_expiry": 60, "owner": "support"},
        ],
        generated_at="2026-06-01T00:00:00+00:00",
    )

    assert report["schema_version"] == "max.source_credential_expiry_report.v1"
    assert report["kind"] == "max.source_credential_expiry_report"
    assert report["summary"]["expired_count"] == 1
    assert report["summary"]["rotation_due_count"] == 1
    assert report["summary"]["valid_count"] == 1
    assert report["summary"]["missing_owner_count"] == 1
    assert [row["status"] for row in report["credential_rows"]] == ["expired", "rotation_due", "valid"]
    assert "github / gh-1: rotate expired credential" in render_source_credential_expiry_report_markdown(report)
    assert json.loads(render_source_credential_expiry_report_json(report))["summary"]["credential_count"] == 3


def test_source_credential_expiry_report_no_action_empty_state() -> None:
    report = build_source_credential_expiry_report([{"source": "github", "days_until_expiry": 30}], rotation_due_days=14)

    assert "No credential rotation actions required" in render_source_credential_expiry_report_markdown(report)
