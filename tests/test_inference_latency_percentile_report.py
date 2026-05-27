from __future__ import annotations

from max.exports.inference_latency_percentile_report import build_inference_latency_percentile_report, render_inference_latency_percentile_report_markdown


def test_inference_latency_percentile_report_computes_sorted_percentiles() -> None:
    report = build_inference_latency_percentile_report(
        [
            {"model": "m", "stage": "draft", "profile": "p", "latency_ms": 1000},
            {"model": "m", "stage": "draft", "profile": "p", "latency_ms": 100},
            {"model": "m", "stage": "draft", "profile": "p", "latency_ms": 500},
            {"model": "m", "stage": "draft", "profile": "p", "latency_ms": -1},
        ],
        sla_ms=800,
    )

    row = report["latency_groups"][0]
    assert row["p50_ms"] == 500
    assert row["p90_ms"] == 1000
    assert row["sla_breached"] is True
    assert report["summary"]["sample_count"] == 3
    assert report["summary"]["breached_group_count"] == 1
    assert "- Samples: 3" in render_inference_latency_percentile_report_markdown(report)
