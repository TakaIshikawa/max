from __future__ import annotations

from max.exports.publication_destination_cost_spike_report import generate_publication_destination_cost_spike_report


def test_publication_destination_cost_spike_report_summarizes_and_sorts_spikes() -> None:
    report = generate_publication_destination_cost_spike_report(
        [
            {"destination": "rss", "current_cost_usd": 12, "baseline_cost_usd": 10, "window_hours": 24, "publication_count": 30},
            {"destination": "slack", "current_cost_usd": 45, "baseline_cost_usd": 10, "window_hours": 24, "publication_count": 8},
            {"destination": "email", "current_cost_usd": 40, "baseline_cost_usd": 20, "window_hours": 24, "publication_count": 9},
            {"destination": "webhook", "current_cost_usd": 8, "baseline_cost_usd": 10, "window_hours": 24, "publication_count": 5},
        ],
        warning_ratio=1.2,
        critical_ratio=2.0,
    )

    assert report["schema_version"] == "max.publication_destination_cost_spike_report.v1"
    assert report["kind"] == "max.publication_destination_cost_spike_report"
    assert report["summary"] == {
        "destination_count": 4,
        "spiking_destination_count": 3,
        "critical_count": 2,
        "excess_cost_usd": 57.0,
    }
    assert [row["destination"] for row in report["destination_rows"]] == ["slack", "email", "rss", "webhook"]
    assert report["destination_rows"][0]["cost_delta"] == 35.0
    assert report["destination_rows"][0]["cost_ratio"] == 4.5
    assert report["destination_rows"][0]["status"] == "critical"


def test_publication_destination_cost_spike_report_handles_zero_baseline_deterministically() -> None:
    report = generate_publication_destination_cost_spike_report(
        [
            {"destination": "new", "current_cost_usd": 5, "baseline_cost_usd": 0},
            {"destination": "idle", "current_cost_usd": 0, "baseline_cost_usd": 0},
        ]
    )

    assert report["summary"]["critical_count"] == 1
    assert report["destination_rows"][0]["destination"] == "new"
    assert report["destination_rows"][0]["cost_ratio"] is None
    assert report["destination_rows"][0]["reason"] == "zero_baseline_spend"
    assert report["destination_rows"][1]["cost_ratio"] == 1.0
