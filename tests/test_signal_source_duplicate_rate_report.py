from __future__ import annotations

from max.exports import generate_signal_source_duplicate_rate_report as exported
from max.exports.signal_source_duplicate_rate_report import generate_signal_source_duplicate_rate_report


def test_signal_source_duplicate_rate_report_flags_and_sorts_sources() -> None:
    report = generate_signal_source_duplicate_rate_report(
        [
            {"source": "rss", "total_count": 10, "duplicate_count": 4},
            {"source": "github", "total_count": 10, "duplicate_count": 2},
            {"source": "alpha", "total_count": 4, "duplicate_count": 1},
        ],
        duplicate_rate_threshold=0.25,
    )

    assert exported is generate_signal_source_duplicate_rate_report
    assert report["summary"] == {
        "source_count": 3,
        "total_count": 24,
        "duplicate_count": 7,
        "flagged_source_count": 1,
        "duplicate_rate_threshold": 0.25,
    }
    assert report["rows"] == [
        {"source": "rss", "total_count": 10, "duplicate_count": 4, "duplicate_rate": 0.4, "status": "high_duplicate_rate"},
        {"source": "alpha", "total_count": 4, "duplicate_count": 1, "duplicate_rate": 0.25, "status": "ok"},
        {"source": "github", "total_count": 10, "duplicate_count": 2, "duplicate_rate": 0.2, "status": "ok"},
    ]


def test_signal_source_duplicate_rate_report_infers_raw_duplicate_keys() -> None:
    report = generate_signal_source_duplicate_rate_report(
        [
            {"source_adapter": "hn", "canonical_url": "https://example.com/a"},
            {"source_adapter": "hn", "canonical_url": "https://example.com/a"},
            {"source_adapter": "hn", "canonical_url": "https://example.com/b"},
            {"signal_source": "blog", "is_duplicate": True},
        ],
        duplicate_rate_threshold=0.3,
    )

    assert report["rows"][0] == {"source": "blog", "total_count": 1, "duplicate_count": 1, "duplicate_rate": 1.0, "status": "high_duplicate_rate"}
    assert report["rows"][1] == {"source": "hn", "total_count": 3, "duplicate_count": 1, "duplicate_rate": 0.3333, "status": "high_duplicate_rate"}


def test_signal_source_duplicate_rate_report_empty_input_returns_valid_summary() -> None:
    report = generate_signal_source_duplicate_rate_report([])

    assert report["schema_version"] == "max.signal_source_duplicate_rate_report.v1"
    assert report["summary"]["source_count"] == 0
    assert report["rows"] == []
