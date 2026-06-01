from __future__ import annotations

import json

from max.exports.source_adapter_latency_regression_report import generate_source_adapter_latency_regression_report


def test_report_flags_only_adapters_over_latency_and_ratio_thresholds() -> None:
    report = generate_source_adapter_latency_regression_report(
        [
            {"adapter": "aws", "current_p95_ms": 1400, "baseline_p95_ms": 1000, "sample_count": 20},
            {"adapter": "github", "current_p95_ms": 900, "baseline_p95_ms": 500, "sample_count": 20},
            {"adapter": "slack", "current_p95_ms": 1300, "baseline_p95_ms": 1200, "sample_count": 20},
        ],
        baseline_p95_ms=1000,
        regression_ratio=1.25,
    )

    assert json.loads(json.dumps(report)) == report
    assert report["summary"]["adapter_count"] == 3
    assert report["summary"]["regressed_adapter_count"] == 1
    assert report["summary"]["worst_regression_ratio"] == 1.4
    assert [row["adapter"] for row in report["rows"]] == ["aws"]


def test_report_skips_missing_or_empty_samples() -> None:
    report = generate_source_adapter_latency_regression_report(
        [
            {"adapter": "aws", "current_p95_ms": 1800, "baseline_p95_ms": 1000, "sample_count": 0},
            {"adapter": "github", "baseline_p95_ms": 1000, "sample_count": 10},
            {"current_p95_ms": 1800, "baseline_p95_ms": 1000, "sample_count": 10},
            {"adapter": "slack", "current_p95_ms": 1800, "sample_count": 10},
        ]
    )

    assert report["rows"] == [{"adapter": "slack", "current_p95_ms": 1800.0, "baseline_p95_ms": 1000.0, "regression_ratio": 1.8, "sample_count": 10, "baseline_sample_count": 10}]
    assert report["summary"]["missing_sample_count"] == 3


def test_report_sorts_by_regression_severity_then_adapter_name() -> None:
    report = generate_source_adapter_latency_regression_report(
        [
            {"adapter": "zeta", "current_p95_ms": 1500, "baseline_p95_ms": 1000, "sample_count": 5},
            {"adapter": "alpha", "current_p95_ms": 1500, "baseline_p95_ms": 1000, "sample_count": 5},
            {"adapter": "beta", "current_p95_ms": 1800, "baseline_p95_ms": 1000, "sample_count": 5},
        ]
    )

    assert [row["adapter"] for row in report["rows"]] == ["beta", "alpha", "zeta"]
