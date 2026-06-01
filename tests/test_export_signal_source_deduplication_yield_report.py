from __future__ import annotations

import json

from max.exports.signal_source_deduplication_yield_report import generate_signal_source_deduplication_yield_report


def test_report_computes_yield_and_duplicate_ratios_per_source() -> None:
    report = generate_signal_source_deduplication_yield_report([{"source": "aws", "raw_signal_count": 100, "unique_signal_count": 40}])

    assert json.loads(json.dumps(report)) == report
    row = report["sources"][0]
    assert row["yield_ratio"] == 0.4
    assert row["duplicate_ratio"] == 0.6
    assert row["duplicate_signal_count"] == 60


def test_report_flags_sources_below_low_yield_threshold() -> None:
    report = generate_signal_source_deduplication_yield_report(
        [
            {"source": "aws", "raw_signal_count": 100, "unique_signal_count": 49},
            {"source": "kubernetes", "raw_signal_count": 100, "unique_signal_count": 50},
            {"source": "empty", "raw_signal_count": 0, "unique_signal_count": 0},
        ],
        low_yield_threshold=0.5,
    )

    assert [row["source"] for row in report["low_yield_sources"]] == ["aws"]
    assert report["summary"]["low_yield_source_count"] == 1


def test_low_yield_sources_sort_by_yield_then_source_name() -> None:
    report = generate_signal_source_deduplication_yield_report(
        [
            {"source": "zeta", "raw_signal_count": 100, "unique_signal_count": 30},
            {"source": "alpha", "raw_signal_count": 100, "unique_signal_count": 30},
            {"source": "beta", "raw_signal_count": 100, "unique_signal_count": 20},
        ]
    )

    assert [row["source"] for row in report["low_yield_sources"]] == ["beta", "alpha", "zeta"]
