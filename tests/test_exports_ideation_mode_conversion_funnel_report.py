from __future__ import annotations

from max.exports import generate_ideation_mode_conversion_funnel_report


def test_ideation_mode_conversion_funnel_report_counts_rates_and_findings() -> None:
    report = generate_ideation_mode_conversion_funnel_report(
        [
            {"ideation_mode": "explore", "evaluated": True, "approved": True, "published": True},
            {"ideation_mode": "explore", "evaluated": True, "rejected": True},
            {"ideation_mode": "exploit", "evaluated": True, "rejected": True},
        ],
        approval_threshold=0.5,
        publication_threshold=0.4,
    )

    explore = next(row for row in report["funnel"] if row["ideation_mode"] == "explore")
    assert explore["generated"] == 2
    assert explore["approval_rate"] == 0.5
    assert explore["publication_rate"] == 0.5
    assert report["findings"][0]["ideation_mode"] == "exploit"

