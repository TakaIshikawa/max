from __future__ import annotations

from max.exports import generate_synthesis_insight_aging_report, render_synthesis_insight_aging_report_markdown


def test_synthesis_insight_aging_groups_by_profile_theme_and_confidence_band() -> None:
    report = generate_synthesis_insight_aging_report(
        [
            {"profile": "p1", "theme": "billing", "confidence": 0.8, "created_at": "2026-04-01T00:00:00+00:00"},
            {"profile": "p1", "theme": "billing", "confidence": 0.9, "created_at": "2026-05-20T00:00:00+00:00", "converted": True},
        ],
        now="2026-05-29T00:00:00+00:00",
    )
    row = report["rows"][0]
    assert row["profile"] == "p1"
    assert row["confidence_band"] == "high"
    assert row["unconverted_count"] == 1
    assert row["oldest_age_days"] == 58
    assert row["severity"] == "critical"
    assert "billing" in render_synthesis_insight_aging_report_markdown(report)
