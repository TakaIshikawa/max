from __future__ import annotations

from max.exports.publisher_webhook_latency_report import (
    generate_publisher_webhook_latency_report,
    render_publisher_webhook_latency_report_markdown,
)


def test_publisher_webhook_latency_report_computes_percentiles_deterministically() -> None:
    report = generate_publisher_webhook_latency_report(
        {
            "attempts": [
                {"id": "a3", "target": "slack", "event_type": "published", "latency_ms": 300},
                {"id": "a1", "target": "slack", "event_type": "published", "latency_ms": 100},
                {"id": "a2", "target": "slack", "event_type": "published", "latency_ms": 200},
            ]
        }
    )

    row = report["groups"][0]
    assert row["p50_latency_ms"] == 200
    assert row["p95_latency_ms"] == 300
    assert row["completed_count"] == 3


def test_publisher_webhook_latency_report_counts_timeouts_and_worst_severity() -> None:
    report = generate_publisher_webhook_latency_report(
        {
            "attempts": [
                {"target": "jira", "event_type": "failed", "latency_ms": 500, "status": "timeout", "retry_count": 1},
                {"target": "jira", "event_type": "failed", "latency_ms": 100, "status": "delivered"},
            ]
        }
    )

    assert report["summary"]["status"] == "critical"
    assert report["groups"][0]["timeout_rate"] == 0.5
    assert report["groups"][0]["retry_attempt_count"] == 1


def test_publisher_webhook_latency_report_groups_by_target_and_event_type_and_renders_markdown() -> None:
    report = generate_publisher_webhook_latency_report(
        [
            {"target": "slack", "event_type": "published", "latency_ms": 100},
            {"target": "slack", "event_type": "retracted", "latency_ms": 150},
            {"target": "jira", "event_type": "published", "latency_ms": 90},
        ]
    )

    assert [(row["target"], row["event_type"]) for row in report["groups"]] == [
        ("jira", "published"),
        ("slack", "published"),
        ("slack", "retracted"),
    ]
    markdown = render_publisher_webhook_latency_report_markdown(report)
    assert "# Publisher Webhook Latency Report" in markdown
    assert "| slack | published |" in markdown
