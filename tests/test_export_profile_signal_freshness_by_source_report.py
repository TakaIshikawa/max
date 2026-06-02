from __future__ import annotations

from max.exports.profile_signal_freshness_by_source_report import generate_profile_signal_freshness_by_source_report


def test_freshness_by_source_groups_sorts_and_counts_buckets() -> None:
    report = generate_profile_signal_freshness_by_source_report([
        {"profile": "growth", "source": "github", "observed_at": "2026-06-01T00:00:00+00:00"},
        {"profile": "growth", "source": "github", "observed_at": "2026-05-25T00:00:00+00:00"},
        {"profile": "growth", "source": "hn"},
        {"profile": "core", "source": "hn", "observed_at": "2026-05-31T00:00:00+00:00"},
    ])

    assert [row["profile"] for row in report["rows"]] == ["core", "growth", "growth"]
    growth_github = report["rows"][1]
    assert growth_github["freshness_buckets"] == {"fresh": 1, "aging": 1, "stale": 0}
    assert report["summary"]["missing_timestamp_count"] == 1


def test_freshness_by_source_empty_input() -> None:
    assert generate_profile_signal_freshness_by_source_report([])["rows"] == []
