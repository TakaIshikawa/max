from __future__ import annotations

import json

from max.exports.signal_source_noise_report import (
    build_signal_source_noise_report,
    render_signal_source_noise_report_json,
    render_signal_source_noise_report_markdown,
)


def test_signal_source_noise_report_computes_rates_and_ranks_sources() -> None:
    report = build_signal_source_noise_report(
        [
            {"source": "rss", "fetched_count": 100, "discarded_count": 10, "duplicate_count": 20, "low_confidence_count": 5, "low_relevance_count": 5},
            {"source": "crm", "fetched_count": 50, "discarded_count": 1},
        ]
    )

    assert report["sources"][0]["source"] == "rss"
    assert report["sources"][0]["noise_rate"] == 0.4
    assert report["sources"][0]["duplicate_rate"] == 0.2
    assert report["sources"][0]["retained_count"] == 60
    assert "Remediation Hints" in render_signal_source_noise_report_markdown(report)
    assert json.loads(render_signal_source_noise_report_json(report))["summary"]["retained_count"] == 109


def test_signal_source_noise_report_handles_zero_fetched_counts() -> None:
    report = build_signal_source_noise_report([{"source": "empty", "duplicate_count": 3}])

    assert report["sources"][0]["noise_rate"] == 0.0
    assert report["sources"][0]["retained_count"] == 0
