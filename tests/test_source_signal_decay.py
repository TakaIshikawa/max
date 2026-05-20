from __future__ import annotations

from max.analysis.source_signal_decay import (
    build_source_signal_decay_analysis,
    render_source_signal_decay_markdown,
)


def test_source_signal_decay_sorts_highest_risk_first() -> None:
    analysis = build_source_signal_decay_analysis(
        [
            {
                "source": "healthy",
                "recent_count": 120,
                "historical_count": 100,
                "newest_timestamp": "2026-05-18",
                "oldest_timestamp": "2026-01-01",
                "quality_score": 0.9,
            },
            {
                "source": "decaying",
                "recent_count": 10,
                "historical_count": 100,
                "newest_timestamp": "2026-03-01",
                "oldest_timestamp": "2026-01-01",
                "quality_score": 0.4,
            },
        ],
        as_of="2026-05-20",
        stale_after_days=45,
    )

    assert analysis["schema_version"] == "max.source_signal_decay.v1"
    assert analysis["kind"] == "max.source_signal_decay"
    assert [row["source"] for row in analysis["decay_rows"]] == ["decaying", "healthy"]
    assert analysis["decay_rows"][0]["decay_risk"] == "critical"
    assert analysis["decay_rows"][0]["volume_trend"] == "rapid_decline"


def test_source_signal_decay_handles_missing_timestamps_with_fallback_status() -> None:
    analysis = build_source_signal_decay_analysis(
        [{"source": "unknown-time", "recent_count": 5, "historical_count": 50}],
        as_of="2026-05-20",
    )

    row = analysis["decay_rows"][0]
    assert row["fallback_status"] == "missing_newest_timestamp"
    assert row["last_seen_age_days"] == 9999
    assert row["decay_risk"] == "critical"
    assert row["volume_trend"] == "unknown_missing_timestamp"
    assert row["recommended_action"] == "repair timestamp ingestion before using this source for freshness decisions"


def test_source_signal_decay_handles_zero_historical_volume() -> None:
    analysis = build_source_signal_decay_analysis(
        [{"source": "new-source", "recent_count": 12, "historical_count": 0, "newest_timestamp": "2026-05-19"}],
        as_of="2026-05-20",
    )

    row = analysis["decay_rows"][0]
    assert row["fallback_status"] == "zero_historical_volume"
    assert row["trend_ratio"] is None
    assert row["decay_risk"] == "high"
    assert row["recommended_action"] == "collect baseline volume before ranking long-term decay"


def test_source_signal_decay_markdown_includes_required_fields() -> None:
    analysis = build_source_signal_decay_analysis(
        [
            {"source": "b", "recent_count": 100, "historical_count": 100, "newest_timestamp": "2026-05-19"},
            {"source": "a", "recent_count": 10, "historical_count": 100, "newest_timestamp": "2026-03-01"},
        ],
        as_of="2026-05-20",
    )

    first = render_source_signal_decay_markdown(analysis)
    second = render_source_signal_decay_markdown(analysis)

    assert first == second
    assert first.startswith("# Source Signal Decay Analysis")
    assert first.index("### a") < first.index("### b")
    assert "- Decay risk:" in first
    assert "- Last-seen age:" in first
    assert "- Volume trend:" in first
    assert "- Recommended action:" in first
