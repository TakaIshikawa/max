from __future__ import annotations

import json

from max.exports.data_deletion_request_readiness_report import (
    KIND,
    SCHEMA_VERSION,
    build_data_deletion_request_readiness_report,
    render_data_deletion_request_readiness_json,
    render_data_deletion_request_readiness_markdown,
)


def test_data_deletion_request_readiness_calculates_sla_and_gaps() -> None:
    records = [
        {
            "request_id": "DDR-1",
            "customer": "Acme",
            "region": "US",
            "request_type": "erasure",
            "status": "in_progress",
            "submitted_at": "2026-05-01",
            "due_at": "2026-05-18",
            "system": "CRM",
            "deletion_owner": "privacy-ops",
            "verification_status": "pending",
            "blocker": "yes",
        },
        {
            "id": "DDR-2",
            "account": "BetaCo",
            "region": "EU",
            "status": "open",
            "submitted_at": "2026-05-10",
            "due_at": "2026-05-22",
            "system": "Warehouse",
            "owner": "",
            "verification_status": "not_started",
            "exception_reason": "Awaiting subprocess export",
        },
        {
            "request_id": "DDR-3",
            "customer": "Cygnus",
            "status": "completed",
            "submitted_at": "2026-05-05",
            "due_at": "2026-05-19",
            "system": "CRM",
            "deletion_owner": "privacy-ops",
            "verification_status": "verified",
        },
    ]

    report = build_data_deletion_request_readiness_report(records, as_of="2026-05-20")

    assert report == build_data_deletion_request_readiness_report(records, as_of="2026-05-20")
    assert json.loads(json.dumps(report)) == report
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"]["request_count"] == 3
    assert report["summary"]["open_request_count"] == 2
    assert report["summary"]["completed_verified_count"] == 1
    assert report["summary"]["sla_risk_count"] == 2
    assert report["summary"]["verification_gap_count"] == 2
    assert [row["request_id"] for row in report["sla_risk_requests"]] == ["DDR-1", "DDR-2"]
    assert [row["request_id"] for row in report["verification_gaps"]] == ["DDR-1", "DDR-2"]
    assert [row["request_id"] for row in report["exception_queue"]] == ["DDR-1", "DDR-2"]
    assert report["request_rows"][0]["days_open"] == 19
    assert report["request_rows"][0]["days_until_due"] == -2
    assert report["request_rows"][1]["days_until_due"] == 2
    assert "DDR-3" not in {row["request_id"] for row in report["sla_risk_requests"]}
    assert "DDR-3" not in {row["request_id"] for row in report["verification_gaps"]}

    markdown = render_data_deletion_request_readiness_markdown(report)
    assert "## Summary" in markdown
    assert "- Requests: 3" in markdown
    assert "## SLA Risk Requests" in markdown
    assert json.loads(render_data_deletion_request_readiness_json(report))["kind"] == KIND


def test_data_deletion_request_readiness_empty_input_returns_zero_counts() -> None:
    report = build_data_deletion_request_readiness_report([], as_of="2026-05-20")

    assert report["summary"]["request_count"] == 0
    assert report["summary"]["open_request_count"] == 0
    assert report["summary"]["sla_risk_count"] == 0
    assert report["request_rows"] == []
    assert report["system_breakdown"] == []
    assert report["sla_risk_requests"] == []
    assert report["verification_gaps"] == []
    assert report["exception_queue"] == []
    assert "No data deletion requests were supplied." in render_data_deletion_request_readiness_markdown(report)
