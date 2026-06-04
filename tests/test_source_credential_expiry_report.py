from __future__ import annotations

import json

from max.exports.source_credential_expiry_report import (
    build_source_credential_expiry_report,
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


def test_source_credential_expiry_renderers_are_deterministic() -> None:
    report = build_source_credential_expiry_report([])

    assert json.loads(render_source_credential_expiry_report_json(report))["kind"] == "max.source_credential_expiry_report"
    assert "No credential rotation actions are due." in render_source_credential_expiry_report_markdown(report)
