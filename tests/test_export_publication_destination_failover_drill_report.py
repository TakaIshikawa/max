from __future__ import annotations

from max.exports import publication_destination_failover_drill_report as report_module
from max.exports.publication_destination_failover_drill_report import (
    generate_publication_destination_failover_drill_report,
)


def test_publication_destination_failover_drill_report_summarizes_risk(monkeypatch) -> None:
    monkeypatch.setattr(report_module, "_now", lambda: report_module.datetime(2026, 6, 1, tzinfo=report_module.timezone.utc))

    report = generate_publication_destination_failover_drill_report(
        [
            {"destination": "slack", "fallback_destination": "email", "last_drill_at": "2026-05-25T00:00:00Z", "outcome": "success"},
            {"destination": "webhook", "fallback_destination": "s3", "last_drill_at": "2026-05-30T00:00:00Z", "outcome": "failed"},
            {"destination": "zendesk", "fallback_destination": "email", "last_drill_at": "2026-01-01T00:00:00Z", "outcome": "success"},
            {"destination": "teams", "fallback_destination": "email", "outcome": "success"},
        ],
        stale_after_days=90,
    )

    assert report["summary"] == {
        "destination_count": 4,
        "risky_destination_count": 3,
        "failed_drill_count": 1,
        "stale_drill_count": 1,
    }
    assert [row["destination"] for row in report["drill_rows"]] == ["webhook", "teams", "zendesk", "slack"]
    assert report["drill_rows"][0]["reason"] == "failed_drill"
    assert report["drill_rows"][1]["days_since_drill"] is None
    assert set(report["drill_rows"][0]) >= {"destination", "fallback_destination", "days_since_drill", "outcome", "reason"}


def test_publication_destination_failover_drill_report_treats_malformed_timestamps_as_missing(monkeypatch) -> None:
    monkeypatch.setattr(report_module, "_now", lambda: report_module.datetime(2026, 6, 1, tzinfo=report_module.timezone.utc))

    report = generate_publication_destination_failover_drill_report(
        [{"destination": "rss", "last_drill_at": "not-a-date", "outcome": "success"}]
    )

    assert report["summary"]["risky_destination_count"] == 1
    assert report["drill_rows"][0]["reason"] == "missing_drill"
    assert report["drill_rows"][0]["days_since_drill"] is None
