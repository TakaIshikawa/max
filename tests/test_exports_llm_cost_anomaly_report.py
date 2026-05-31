from __future__ import annotations

from max.exports.llm_cost_anomaly_report import generate_llm_cost_anomaly_report, render_llm_cost_anomaly_report_markdown


def test_llm_cost_anomaly_calculates_variance_and_filters_healthy_rows() -> None:
    report = generate_llm_cost_anomaly_report(
        [
            {"provider": "openai", "model": "m", "stage": "synthesis", "profile": "p", "expected_cost": 10, "actual_cost": 16},
            {"provider": "anthropic", "model": "m", "stage": "draft", "profile": "p", "expected_cost": 10, "actual_cost": 11},
        ],
        anomaly_threshold=0.2,
    )

    assert len(report["rows"]) == 1
    assert report["rows"][0]["variance"] == 6
    assert report["rows"][0]["variance_pct"] == 0.6
    assert report["rows"][0]["severity"] == "critical"
    assert "expected 10.0, actual 16.0" in render_llm_cost_anomaly_report_markdown(report)
