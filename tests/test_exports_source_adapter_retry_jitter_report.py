from __future__ import annotations

import json

from max.exports.source_adapter_retry_jitter_report import (
    generate_source_adapter_retry_jitter_report,
    render_source_adapter_retry_jitter_report_json,
    render_source_adapter_retry_jitter_report_markdown,
)


def test_source_adapter_retry_jitter_report_classifies_and_summarizes_risks() -> None:
    report = generate_source_adapter_retry_jitter_report(
        [
            {"source": "  Zendesk  ", "retry_count": "2", "min_delay_ms": 100, "max_delay_ms": 500, "observed_delay_ms": 220, "jitter_enabled": False},
            {"source": "GitHub", "retry_count": 3, "min_delay_ms": 200, "max_delay_ms": 240, "observed_delay_ms": 220, "jitter_enabled": True},
            {"source": "Slack", "retry_count": 6, "min_delay_ms": 100, "max_delay_ms": 700, "observed_delay_ms": 410, "jitter_enabled": True},
            {"source": "Airtable", "retry_count": 1, "min_delay_ms": -10, "max_delay_ms": "bad", "observed_delay_ms": None, "jitter_enabled": True},
            {"source": "Asana", "retry_count": 0, "min_delay_ms": 0, "max_delay_ms": 0, "observed_delay_ms": 0, "jitter_enabled": False},
        ]
    )

    assert report["summary"] == {
        "adapter_count": 5,
        "risky_adapter_count": 4,
        "missing_jitter_count": 1,
        "excessive_retry_count": 1,
        "low_jitter_count": 2,
    }
    assert [row["status"] for row in report["adapter_rows"]] == ["missing_jitter", "low_jitter", "low_jitter", "excessive_retry", "healthy"]
    assert report["adapter_rows"][0]["source"] == "Zendesk"
    assert report["adapter_rows"][1]["jitter_span_ms"] == 40
    assert report["adapter_rows"][2]["min_delay_ms"] == 0
    assert report["adapter_rows"][-1]["source"] == "Asana"


def test_source_adapter_retry_jitter_report_renderers_are_deterministic() -> None:
    report = generate_source_adapter_retry_jitter_report([{"source": "GitHub", "retry_count": 0}])

    assert json.loads(render_source_adapter_retry_jitter_report_json(report))["kind"] == "max.source_adapter_retry_jitter_report"
    assert "GitHub: healthy" in render_source_adapter_retry_jitter_report_markdown(report)
