from __future__ import annotations

import json

from max.exports.publisher_webhook_retry_storm_report import (
    generate_publisher_webhook_retry_storm_report,
    render_publisher_webhook_retry_storm_report_json,
    render_publisher_webhook_retry_storm_report_markdown,
)


def test_publisher_webhook_retry_storm_report_groups_and_sorts_storms() -> None:
    records = [
        {"destination": "zendesk", "webhook_id": "b", "attempted_at": f"2026-06-01T00:0{i}:00Z", "retry": True}
        for i in range(5)
    ] + [
        {"destination": "asana", "endpoint": "/hook", "attempted_at": f"2026-06-01T00:0{i}:00Z", "retry": True}
        for i in range(10)
    ]

    report = generate_publisher_webhook_retry_storm_report(records, retry_threshold=5, window_minutes=10)

    assert report["summary"]["attempt_count"] == 15
    assert report["summary"]["storm_group_count"] == 2
    assert report["summary"]["affected_destination_count"] == 2
    assert report["summary"]["highest_severity"] == "high"
    assert [row["destination"] for row in report["storm_rows"]] == ["asana", "zendesk"]


def test_publisher_webhook_retry_storm_report_handles_missing_identifiers_and_configurable_threshold() -> None:
    report = generate_publisher_webhook_retry_storm_report(
        [{"destination": "", "attempted_at": "bad", "retry_count": 1} for _ in range(3)],
        retry_threshold=3,
        window_minutes=1,
    )

    row = report["storm_rows"][0]
    assert row["destination"] == "unknown-destination"
    assert row["webhook_identifier"] == "unknown-webhook"
    assert row["retry_burst_count"] == 1


def test_publisher_webhook_retry_storm_report_renderers() -> None:
    report = generate_publisher_webhook_retry_storm_report(
        [{"destination": "slack", "webhook_id": "w1", "retry": True} for _ in range(5)]
    )

    rendered = render_publisher_webhook_retry_storm_report_json(report)
    assert rendered.endswith("\n")
    assert json.loads(rendered)["summary"]["storm_group_count"] == 1

    markdown = render_publisher_webhook_retry_storm_report_markdown(report)
    assert "increase backoff" in markdown
