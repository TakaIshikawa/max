from __future__ import annotations

from max.exports import generate_budget_burn_rate_report as exported
from max.exports.budget_burn_rate_report import generate_budget_burn_rate_report


def test_budget_burn_rate_report_handles_empty_samples() -> None:
    report = generate_budget_burn_rate_report([])

    assert exported is generate_budget_burn_rate_report
    assert report["summary"]["status"] == "ok"
    assert report["summary"]["total_spend"] == 0
    assert report["rows"] == []


def test_budget_burn_rate_report_groups_and_computes_rates() -> None:
    report = generate_budget_burn_rate_report(
        [
            {"profile": "core", "pipeline_stage": "fetch", "spend": 10, "budget": 200, "timestamp": "2026-06-01T00:00:00+00:00"},
            {"profile": "core", "pipeline_stage": "fetch", "cost": 14, "timestamp": "2026-06-01T06:00:00+00:00"},
            {"profile": "core", "pipeline_stage": "publish", "amount": 2, "budget": 100, "timestamp": "2026-06-01T00:00:00+00:00"},
        ]
    )

    fetch = next(row for row in report["rows"] if row["pipeline_stage"] == "fetch")
    assert fetch["sample_count"] == 2
    assert fetch["total_spend"] == 24
    assert fetch["elapsed_hours"] == 6
    assert fetch["burn_rate_per_hour"] == 4
    assert fetch["projected_daily_spend"] == 96
    assert fetch["remaining_budget"] == 176
    assert fetch["status"] == "ok"


def test_budget_burn_rate_report_classifies_watch_and_overrun() -> None:
    report = generate_budget_burn_rate_report(
        [
            {"profile": "core", "stage": "watch", "spend": 81, "budget": 100, "timestamp": "2026-06-01T00:00:00+00:00"},
            {"profile": "core", "stage": "watch", "spend": 0, "timestamp": "2026-06-02T00:00:00+00:00"},
            {"profile": "core", "stage": "over", "spend": 10, "budget": 100, "timestamp": "2026-06-01T00:00:00+00:00"},
            {"profile": "core", "stage": "over", "spend": 10, "timestamp": "2026-06-01T01:00:00+00:00"},
        ]
    )

    assert report["rows"][0]["pipeline_stage"] == "over"
    assert report["rows"][0]["status"] == "overrun"
    assert next(row for row in report["rows"] if row["pipeline_stage"] == "watch")["status"] == "watch"
