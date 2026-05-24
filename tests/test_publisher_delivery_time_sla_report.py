from __future__ import annotations

import json

from max.exports.publisher_delivery_time_sla_report import (
    KIND,
    build_publisher_delivery_time_sla_report,
    render_publisher_delivery_time_sla_report_json,
)


def test_publisher_delivery_time_sla_flags_completed_and_pending() -> None:
    report = build_publisher_delivery_time_sla_report(
        [
            {"artifact_id": "a1", "destination": "slack", "requested_at": "2026-05-20T00:00:00+00:00", "completed_at": "2026-05-20T00:20:00+00:00", "sla_minutes": 30},
            {"artifact_id": "a2", "destination": "email", "requested_at": "2026-05-20T00:00:00+00:00", "completed_at": "2026-05-20T02:00:00+00:00", "sla_minutes": 60},
            {"artifact_id": "a3", "destination": "email", "requested_at": "2026-05-20T01:00:00+00:00", "sla_minutes": 30},
        ],
        as_of="2026-05-20T02:00:00+00:00",
    )

    assert report["kind"] == KIND
    assert report["summary"]["average_delivery_minutes"] == 66.67
    assert report["summary"]["p95_delivery_minutes"] == 120.0
    assert report["summary"]["breach_count"] == 2
    assert report["delivery_rows"][0]["artifact_id"] == "a2"
    assert report["summary"]["destination_summaries"][0]["destination"] == "email"
    assert json.loads(render_publisher_delivery_time_sla_report_json(report))["summary"]["breach_count"] == 2


def test_publisher_delivery_time_sla_defaults_missing_fields() -> None:
    report = build_publisher_delivery_time_sla_report([{}])

    assert report["delivery_rows"][0]["artifact_id"] == "unknown-artifact-1"
    assert report["delivery_rows"][0]["status"] == "met"
