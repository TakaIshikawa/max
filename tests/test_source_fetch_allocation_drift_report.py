from __future__ import annotations

from max.exports.source_fetch_allocation_drift_report import generate_source_fetch_allocation_drift_report


def test_source_fetch_allocation_drift_calculates_streaks_and_suppression() -> None:
    report = generate_source_fetch_allocation_drift_report(
        [
            {"sources": [{"source": "GitHub", "planned_share": 0.5, "actual_share": 0.3}, {"source": "Slack", "planned_share": 0.2, "actual_share": 0.35}, {"source": "Zendesk", "planned_share": 0.3, "actual_share": 0.0, "suppressed": True}]},
            {"sources": [{"source": "GitHub", "planned_share": 0.5, "actual_share": 0.35}, {"source": "Slack", "planned_share": 0.2, "actual_share": 0.32}, {"source": "Zendesk", "planned_share": 0.3, "actual_share": 0.0, "suppressed": True}]},
        ],
        drift_threshold=0.1,
        sustained_runs=2,
    )

    assert report["kind"] == "max.source_fetch_allocation_drift_report"
    assert report["summary"] == {"source_count": 3, "sustained_drift_count": 2, "suppressed_source_count": 1}
    assert [row["source"] for row in report["source_rows"]] == ["GitHub", "Slack", "Zendesk"]
    assert report["source_rows"][0]["underfetch_streak"] == 2
    assert report["source_rows"][1]["overfetch_streak"] == 2
    assert report["source_rows"][2]["recommendation"] == "resolve suppression before judging allocation fairness"
